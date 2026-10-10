import XCTest
@testable import Inbox

final class ThreadCacheTests: XCTestCase {
    private var directory: URL!

    override func setUp() {
        super.setUp()
        directory = FileManager.default.temporaryDirectory.appending(path: "thread-cache-tests-\(UUID().uuidString)", directoryHint: .isDirectory)
        ThreadCache.directory = directory
        ThreadCache.clear()
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: directory)
        super.tearDown()
    }

    private func detail(_ id: String, messages: Int, updatedAt: String = "2026-01-01T00:00:00Z") -> ConversationDetail {
        let row = Conversation(
            id: id, clientId: "c1", agentId: "a1", title: "Case \(id)", mode: .human, status: .open, channel: "widget", externalChatId: nil,
            contactName: "Ana", contactId: nil, contactEmail: nil, preview: "hello", unread: false, unreadCount: 0, assigneeId: nil, assigneeName: nil,
            teamId: nil, teamName: nil, replyWindowUntil: nil, replyWindowOpen: true, humanReplyWindowOpen: nil, humanReplyWindowUntil: nil,
            replyBlockReason: nil, socialChannelId: nil, channelCapabilities: nil, lastInboundAt: nil, resolvedAt: nil, firstReplyAt: nil,
            takenOverAt: nil, waitingSince: nil, createdAt: "2026-01-01T00:00:00Z", updatedAt: updatedAt
        )
        var result = ConversationDetail(opening: row)
        result.messages = (0..<messages).map { index in
            Message(id: "\(id)-m\(index)", role: index.isMultiple(of: 2) ? "user" : "assistant", kind: "message", activity: nil, content: "text \(index)",
                    senderType: "human", senderName: nil, externalMessageId: nil, deliveryStatus: nil, deliveryError: nil, reaction: nil,
                    incomingReaction: nil, quotedMessageId: nil, createdAt: "2026-01-01T00:00:\(String(format: "%02d", index % 60))Z", attachments: [])
        }
        return result
    }

    func testSaveKeepsTheLatestMessagesAndTheUpdateStamp() throws {
        ThreadCache.save(detail("t1", messages: ThreadCache.messageLimit + 15, updatedAt: "2026-02-02T00:00:00Z"))
        let loaded = try XCTUnwrap(ThreadCache.load("t1"))
        XCTAssertEqual(loaded.messages.count, ThreadCache.messageLimit)
        XCTAssertEqual(loaded.messages.last?.id, "t1-m\(ThreadCache.messageLimit + 14)")
        XCTAssertEqual(ThreadCache.updatedAt("t1"), "2026-02-02T00:00:00Z")
        XCTAssertNil(ThreadCache.load("missing"))
        XCTAssertNil(ThreadCache.updatedAt("missing"))
    }

    func testOldestThreadsLeaveWhenTheLimitIsReachedAndClearRemovesAll() {
        for index in 0..<(ThreadCache.threadLimit + 3) {
            ThreadCache.save(detail("t\(index)", messages: 2))
            // Distinct modification dates so the order is the one saved.
            let path = directory.appending(path: "t\(index).json").path()
            try? FileManager.default.setAttributes([.modificationDate: Date(timeIntervalSince1970: 1_000 + Double(index))], ofItemAtPath: path)
        }
        ThreadCache.save(detail("newest", messages: 1))
        XCTAssertNil(ThreadCache.load("t0"))
        XCTAssertNotNil(ThreadCache.load("newest"))
        XCTAssertNotNil(ThreadCache.load("t\(ThreadCache.threadLimit + 2)"))
        ThreadCache.clear()
        XCTAssertNil(ThreadCache.load("newest"))
    }
}
