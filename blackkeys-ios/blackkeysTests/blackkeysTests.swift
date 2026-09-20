import Foundation
import Testing
import WebKit
@testable import blackkeys

@MainActor
@Suite(.serialized)
struct blackkeysTests {
    @Test func signInSendsExpectedRequestAndDecodesToken() async throws {
        let session = makeSession { request in
            StubURLProtocol.recordedRequest = request
            return response(statusCode: 200, body: #"{"token":"issued-token"}"#)
        }
        let service = AuthService(baseURL: URL(string: "https://api.example.com")!, session: session)

        let authSession = try await service.signIn(username: "alice", password: "exact password ")

        #expect(authSession.username == "alice")
        #expect(authSession.token == "issued-token")
        let request = try #require(StubURLProtocol.recordedRequest)
        #expect(request.httpMethod == "POST")
        #expect(request.url == URL(string: "https://api.example.com/v1/auth/signin"))
        #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
        let body = try #require(requestBody(from: request))
        let json = try #require(try JSONSerialization.jsonObject(with: body) as? [String: String])
        #expect(json == ["username": "alice", "password": "exact password "])
    }

    @Test func missingBaseURLIsAConfigurationError() async {
        let service = AuthService(baseURL: nil, session: makeSession { _ in
            response(statusCode: 200, body: #"{"token":"unused"}"#)
        })

        await expect(.invalidConfiguration, from: service)
    }

    @Test func badRequestIsMappedToInvalidRequest() async {
        await expectStatus(400, as: .invalidRequest)
    }

    @Test func unauthorizedIsMappedToInvalidCredentials() async {
        await expectStatus(401, as: .invalidCredentials)
    }

    @Test func unavailableServiceIsMappedToServiceUnavailable() async {
        await expectStatus(503, as: .serviceUnavailable)
    }

    @Test func malformedPayloadIsMappedToMalformedResponse() async {
        let service = AuthService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in response(statusCode: 200, body: #"{"token":42}"#) }
        )

        await expect(.malformedResponse, from: service)
    }

    @Test func transportFailureIsMappedToNetworkFailure() async {
        let service = AuthService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in throw URLError(.notConnectedToInternet) }
        )

        await expect(.networkFailure, from: service)
    }

    private func expectStatus(_ statusCode: Int, as expectedError: AuthServiceError) async {
        let service = AuthService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in response(statusCode: statusCode, body: "{}") }
        )

        await expect(expectedError, from: service)
    }

    private func expect(_ expectedError: AuthServiceError, from service: AuthService) async {
        do {
            _ = try await service.signIn(username: "alice", password: "password")
            Issue.record("Expected \(expectedError) to be thrown")
        } catch let error as AuthServiceError {
            #expect(error == expectedError)
        } catch {
            Issue.record("Expected AuthServiceError, got \(error)")
        }
    }
}

private func makeSession(
    handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
) -> URLSession {
    StubURLProtocol.handler = handler
    StubURLProtocol.recordedRequest = nil

    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [StubURLProtocol.self]
    return URLSession(configuration: configuration)
}

private func response(statusCode: Int, body: String) -> (HTTPURLResponse, Data) {
    let url = URL(string: "https://api.example.com/v1/auth/signin")!
    return (HTTPURLResponse(url: url, statusCode: statusCode, httpVersion: nil, headerFields: nil)!, Data(body.utf8))
}

private func requestBody(from request: URLRequest) -> Data? {
    if let body = request.httpBody {
        return body
    }

    guard let stream = request.httpBodyStream else {
        return nil
    }

    stream.open()
    defer { stream.close() }

    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 1_024)
    while true {
        let count = stream.read(&buffer, maxLength: buffer.count)
        guard count >= 0 else {
            return nil
        }
        guard count > 0 else {
            return data
        }
        data.append(buffer, count: count)
    }
}

private final class StubURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    nonisolated(unsafe) static var recordedRequest: URLRequest?

    override class func canInit(with request: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        do {
            guard let handler = Self.handler else {
                throw URLError(.unknown)
            }
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

@Suite
struct MapGeolocationPermissionPolicyTests {
    @Test func trustedOriginPrompts() {
        let decision = MapGeolocationPermissionPolicy.decision(
            forProtocol: "https",
            host: "demos.mappedin.com",
            port: 443
        )

        #expect(decision == .prompt)
    }

    @Test func wrongProtocolIsDenied() {
        let decision = MapGeolocationPermissionPolicy.decision(
            forProtocol: "http",
            host: "demos.mappedin.com",
            port: 443
        )

        #expect(decision == .deny)
    }

    @Test func wrongHostIsDenied() {
        let decision = MapGeolocationPermissionPolicy.decision(
            forProtocol: "https",
            host: "evil.example.com",
            port: 443
        )

        #expect(decision == .deny)
    }

    @Test func wrongPortIsDenied() {
        let decision = MapGeolocationPermissionPolicy.decision(
            forProtocol: "https",
            host: "demos.mappedin.com",
            port: 8443
        )

        #expect(decision == .deny)
    }
}
