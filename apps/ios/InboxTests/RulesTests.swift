import XCTest
@testable import Inbox

final class RulesTests: XCTestCase {
    func testHostedServerAcceptsNameOrMatchingAddress() {
        let template = "https://{workspace}.example.com"
        XCTAssertEqual(HostedServer.resolve("Acme", template: template), "https://acme.example.com")
        XCTAssertEqual(HostedServer.resolve("https://acme.example.com", template: template), "https://acme.example.com")
        XCTAssertNil(HostedServer.resolve("https://acme.other.com", template: template))
        XCTAssertNil(HostedServer.resolve("https://acme.example.com/path", template: template))
        XCTAssertNil(HostedServer.resolve("bad name", template: template))
    }

    func testServerNormalization() {
        XCTAssertEqual(APIClient.normalizeServerURL("example.com/"), "https://example.com")
        XCTAssertEqual(APIClient.normalizeServerURL("10.0.0.4:8000"), "http://10.0.0.4:8000")
        XCTAssertEqual(APIClient.normalizeServerURL("https://chat.example.com/api"), "https://chat.example.com")
        XCTAssertEqual(APIClient.normalizeServerURL("   "), "")
    }

    func testPhoneFromWhatsAppAddress() {
        XCTAssertEqual(Conversations.phone(from: "573001234567@s.whatsapp.net"), "+573001234567")
        XCTAssertNil(Conversations.phone(from: "120363@g.us"))
        XCTAssertNil(Conversations.phone(from: "12345@s.whatsapp.net"))
        XCTAssertEqual(Conversations.initial("+573001234567"), "5")
        XCTAssertEqual(Conversations.initial("  ana"), "A")
        XCTAssertEqual(Conversations.initial(""), "?")
    }

    func testNotificationTargetRequiresMatchingClient() {
        XCTAssertEqual(NotificationTarget.conversationId(in: ["conversation_id": "c1"], clientId: "k1"), "c1")
        XCTAssertEqual(NotificationTarget.conversationId(in: ["conversation_id": "c1", "client_id": "k1"], clientId: "k1"), "c1")
        XCTAssertNil(NotificationTarget.conversationId(in: ["conversation_id": "c1", "client_id": "k2"], clientId: "k1"))
        XCTAssertNil(NotificationTarget.conversationId(in: ["conversation_id": ""], clientId: "k1"))
    }

    func testRichTextStripsMarkers() {
        let text = String(RichText.attributed("hello **bold** and *it* and `code`").characters)
        XCTAssertEqual(text, "hello bold and it and code")
    }

    func testCannedInterpolationLeavesUnknownKeys() {
        let vars = InboxRules.CannedVariables(contactName: "Ana", contactPhone: "+57300", contactEmail: "", agentName: "Juan")
        XCTAssertEqual(InboxRules.interpolate("Hi {contact_name}, {unknown}", vars), "Hi Ana, {unknown}")
        XCTAssertEqual(InboxRules.interpolate("{agent_name} / {my_name} / {contact_phone} / {contact_email}", vars), "Juan / Juan / +57300 / {contact_email}")
    }

    func testDurationFormatting() {
        let s = WorkspaceStrings.en
        XCTAssertEqual(Reports.duration(nil, s), "No data")
        XCTAssertEqual(Reports.duration(45, s), "45 s")
        XCTAssertEqual(Reports.duration(150, s), "3 min")
        XCTAssertEqual(Reports.duration(3900, s), "1 h 5 min")
    }
}
