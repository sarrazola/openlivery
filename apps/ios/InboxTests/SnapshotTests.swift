import XCTest
@testable import Inbox

final class SnapshotTests: XCTestCase {
    private var directory: URL!

    override func setUp() {
        super.setUp()
        directory = FileManager.default.temporaryDirectory.appending(path: "snapshot-tests-\(UUID().uuidString)", directoryHint: .isDirectory)
        SnapshotStore.directory = directory
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: directory)
        super.tearDown()
    }

    private func session(token: String) -> Session {
        Session(
            token: token, portalSlug: "acme", clientId: "c1", userId: "u1", userName: "Ana", role: nil, permissions: nil,
            branding: Branding(agencyName: "Agency", clientName: "Acme", portalTitle: "Inbox", brandColor: "#123456", agencyLogoUrl: nil, clientLogoUrl: nil),
            push: PushConfig(enabled: false, provider: "none"), apiVersion: 1, privacy: nil
        )
    }

    private func conversation(_ id: String) -> Conversation {
        Conversation(
            id: id, clientId: "c1", agentId: "a1", title: "Case \(id)", mode: .human, status: .open, channel: "widget", externalChatId: nil,
            contactName: "Ana", contactId: nil, contactEmail: nil, preview: "hello", unread: false, unreadCount: 0, assigneeId: nil, assigneeName: nil,
            teamId: nil, teamName: nil, replyWindowUntil: nil, replyWindowOpen: true, humanReplyWindowOpen: nil, humanReplyWindowUntil: nil,
            replyBlockReason: nil, socialChannelId: nil, channelCapabilities: nil, lastInboundAt: nil, resolvedAt: nil, firstReplyAt: nil,
            takenOverAt: nil, waitingSince: nil, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z"
        )
    }

    func testRoundTripJoinsTheTokenBackAndKeepsItOffDisk() throws {
        let rows = (0..<3).map { conversation("k\($0)") }
        SnapshotStore.save(server: "https://acme.example.com", session: session(token: "secret"), conversations: rows, summary: InboxSummary(open: 3, resolved: 1, human: 2, ai: 1, unread: 1, mine: 1, unassigned: 0))
        let raw = try String(contentsOf: directory.appending(path: "snapshot.v1.json"), encoding: .utf8)
        XCTAssertFalse(raw.contains("secret"))

        let loaded = try XCTUnwrap(SnapshotStore.load(server: "https://acme.example.com", token: "secret"))
        XCTAssertEqual(loaded.session.token, "secret")
        XCTAssertEqual(loaded.session.branding.clientName, "Acme")
        XCTAssertEqual(loaded.conversations.map(\.id), ["k0", "k1", "k2"])
        XCTAssertEqual(loaded.summary?.open, 3)
    }

    func testSnapshotIsScopedToItsServerAndCappedAndClearable() throws {
        let rows = (0..<(SnapshotStore.rowLimit + 5)).map { conversation("k\($0)") }
        SnapshotStore.save(server: "https://acme.example.com", session: session(token: "t"), conversations: rows, summary: nil)
        XCTAssertNil(SnapshotStore.load(server: "https://other.example.com", token: "t"))
        XCTAssertNil(SnapshotStore.load(server: "https://acme.example.com", token: ""))
        XCTAssertEqual(SnapshotStore.load(server: "https://acme.example.com", token: "t")?.conversations.count, SnapshotStore.rowLimit)
        SnapshotStore.clear()
        XCTAssertNil(SnapshotStore.load(server: "https://acme.example.com", token: "t"))
    }
}
