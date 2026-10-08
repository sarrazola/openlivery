import Foundation

/// Talks to the server this session was opened against.
///
/// The server is not baked in: a person signs in by typing the address of the
/// instance their agency runs, so every call takes the base URL from the stored
/// session. Sign-in resolves the portal from the credentials and returns a token
/// that is sent as a bearer credential from then on.
struct APIError: Error, LocalizedError, Equatable {
    let message: String
    let status: Int

    var errorDescription: String? { message }
    var isUnauthorized: Bool { status == 401 }
}

final class APIClient: @unchecked Sendable {
    static let shared = APIClient()

    private let session: URLSession
    private let lock = NSLock()
    /// The app closes this gate while permission or session refresh is pending.
    private var access: [String: Bool] = [:]

    init() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 30
        configuration.httpCookieAcceptPolicy = .never
        configuration.httpShouldSetCookies = false
        configuration.waitsForConnectivity = false
        session = URLSession(configuration: configuration)
    }

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    func setSessionAccess(_ session: Session, _ allowed: Bool) {
        lock.lock(); defer { lock.unlock() }
        access[session.token] = allowed
    }

    func requireSessionAccess(_ token: String?) throws {
        guard let token else { return }
        lock.lock(); defer { lock.unlock() }
        if access[token] == false { throw APIError(message: PrivacyStrings.current.permissionRequired, status: 428) }
    }

    /// Accepts what a person actually types: "10.0.0.4:8000", "example.com", a full URL.
    static func normalizeServerURL(_ input: String) -> String {
        var value = input.trimmingCharacters(in: .whitespacesAndNewlines)
        while value.hasSuffix("/") { value.removeLast() }
        guard !value.isEmpty else { return "" }
        if value.range(of: "^https?://", options: [.regularExpression, .caseInsensitive]) == nil {
            let isLocal = value.range(of: "^(localhost|127\\.0\\.0\\.1|10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[01])\\.)", options: [.regularExpression, .caseInsensitive]) != nil
            value = "\(isLocal ? "http" : "https")://\(value)"
        }
        if value.hasSuffix("/api") { value.removeLast(4) }
        return value
    }

    static func portalPath(_ session: Session, _ path: String) -> String {
        let slug = session.portalSlug.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? session.portalSlug
        return "/portal/\(slug)\(path)"
    }

    static func encodePathComponent(_ value: String) -> String {
        var allowed = CharacterSet.urlPathAllowed
        allowed.remove(charactersIn: "/:@")
        return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
    }

    private func url(_ server: String, _ path: String) throws -> URL {
        guard let url = URL(string: "\(server)/api\(path)") else { throw APIError(message: Strings.current.signIn.invalidServer, status: 0) }
        return url
    }

    /// API failures are parsed once for JSON replies and multipart uploads alike.
    private func decode<T: Decodable>(_ data: Data, _ response: URLResponse, fallback: String) throws -> T {
        guard let http = response as? HTTPURLResponse else { throw APIError(message: fallback, status: 0) }
        guard (200...299).contains(http.statusCode) else {
            var message = fallback
            if let body = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                if let detail = body["detail"] as? String { message = detail }
                else if let detail = body["detail"] as? [[String: Any]], let first = detail.first?["msg"] as? String { message = first }
            }
            throw APIError(message: message, status: http.statusCode)
        }
        if T.self == Empty.self { return Empty() as! T }
        if http.statusCode == 204 || data.isEmpty { throw APIError(message: fallback, status: http.statusCode) }
        do { return try APIClient.decoder.decode(T.self, from: data) }
        catch { throw APIError(message: fallback, status: http.statusCode) }
    }

    struct Empty: Decodable {}

    func request<T: Decodable>(
        _ server: String, _ path: String, method: String = "GET", body: (any Encodable)? = nil, token: String? = nil
    ) async throws -> T {
        let gateExempt = path == "/mobile/session" || (path.hasPrefix("/mobile/devices/") && method == "DELETE")
        if !gateExempt { try requireSessionAccess(token) }
        var request = URLRequest(url: try url(server, path))
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = try APIClient.encoder.encode(AnyEncodable(body))
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        do {
            let (data, response) = try await session.data(for: request)
            return try decode(data, response, fallback: Strings.current.errors.generic)
        } catch let error as APIError { throw error }
        catch is CancellationError { throw CancellationError() }
        catch let error as URLError where error.code == .cancelled { throw CancellationError() }
        catch { throw APIError(message: Strings.current.errors.unreachable, status: 0) }
    }

    /// A request to an absolute address, for endpoints outside a workspace's `/api`.
    func request<T: Decodable>(url: URL, method: String = "GET", body: (any Encodable)? = nil) async throws -> T {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = try APIClient.encoder.encode(AnyEncodable(body))
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        do {
            let (data, response) = try await session.data(for: request)
            return try decode(data, response, fallback: Strings.current.errors.generic)
        } catch let error as APIError { throw error }
        catch is CancellationError { throw CancellationError() }
        catch { throw APIError(message: Strings.current.errors.unreachable, status: 0) }
    }

    func requestVoid(_ server: String, _ path: String, method: String, body: (any Encodable)? = nil, token: String? = nil) async throws {
        let _: Empty = try await request(server, path, method: method, body: body, token: token)
    }

    /// Send a file into a conversation: a photo, a voice note, anything.
    ///
    /// Multipart rather than JSON, because the server's portal endpoint is the
    /// same one the browser posts to. The app is a second client of it, not a
    /// second implementation.
    func upload<T: Decodable>(_ server: String, _ path: String, token: String, file: OutgoingFile, caption: String) async throws -> T {
        try requireSessionAccess(token)
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: try url(server, path))
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        let fileData: Data
        do { fileData = try Data(contentsOf: file.url) }
        catch { throw APIError(message: "\(Strings.current.errors.sendFile): \(error.localizedDescription)", status: 0) }
        var body = Data()
        func append(_ text: String) { body.append(text.data(using: .utf8)!) }
        let safeName = file.name.replacingOccurrences(of: "\"", with: "_")
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"file\"; filename=\"\(safeName)\"\r\n")
        append("Content-Type: \(file.mime)\r\n\r\n")
        body.append(fileData)
        append("\r\n--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"caption\"\r\n\r\n")
        append(caption)
        append("\r\n--\(boundary)--\r\n")
        request.httpBody = body
        do {
            let (data, response) = try await session.data(for: request)
            return try decode(data, response, fallback: Strings.current.errors.sendFile)
        } catch let error as APIError { throw error }
        catch is CancellationError { throw CancellationError() }
        catch { throw APIError(message: "\(Strings.current.errors.sendFile): \(error.localizedDescription)", status: 0) }
    }

    /// Attachments are behind the session, so they cannot be plain image URLs.
    func data(_ url: URL, token: String) async throws -> Data {
        try requireSessionAccess(token)
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw APIError(message: Strings.current.errors.generic, status: (response as? HTTPURLResponse)?.statusCode ?? 0)
        }
        return data
    }
}

/// A file staged for sending, as the pickers and the recorder produce it.
struct OutgoingFile: Equatable {
    var url: URL
    var name: String
    var mime: String

    var isImage: Bool { mime.hasPrefix("image/") }
    var isAudio: Bool { mime.hasPrefix("audio/") }
}

private struct AnyEncodable: Encodable {
    let value: any Encodable
    init(_ value: any Encodable) { self.value = value }
    func encode(to encoder: Encoder) throws { try value.encode(to: encoder) }
}
