import Foundation

struct AuthSession: Equatable, Sendable {
    let username: String
    let token: String
}

enum AuthServiceError: Error, Equatable, LocalizedError, Sendable {
    case invalidConfiguration
    case invalidRequest
    case invalidCredentials
    case serviceUnavailable
    case malformedResponse
    case networkFailure

    var errorDescription: String? {
        switch self {
        case .invalidConfiguration:
            "Sign-in is not configured for this build."
        case .invalidRequest:
            "Please check your username and password."
        case .invalidCredentials:
            "The username or password is incorrect."
        case .serviceUnavailable:
            "The sign-in service is temporarily unavailable."
        case .malformedResponse:
            "The sign-in service returned an unexpected response."
        case .networkFailure:
            "Unable to reach the sign-in service. Please try again."
        }
    }
}

struct AuthService {
    private let baseURL: URL?
    private let session: URLSession

    init(baseURL: URL? = APIConfiguration.baseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    func signIn(username: String, password: String) async throws -> AuthSession {
        guard let baseURL, let endpoint = signInEndpoint(from: baseURL) else {
            throw AuthServiceError.invalidConfiguration
        }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        do {
            request.httpBody = try JSONEncoder().encode(Credentials(username: username, password: password))
        } catch {
            throw AuthServiceError.malformedResponse
        }

        do {
            let (data, response) = try await session.data(for: request)
            guard let response = response as? HTTPURLResponse else {
                throw AuthServiceError.malformedResponse
            }

            switch response.statusCode {
            case 200 ... 299:
                break
            case 400:
                throw AuthServiceError.invalidRequest
            case 401:
                throw AuthServiceError.invalidCredentials
            case 503:
                throw AuthServiceError.serviceUnavailable
            default:
                throw AuthServiceError.malformedResponse
            }

            let responseBody: SignInResponse
            do {
                responseBody = try JSONDecoder().decode(SignInResponse.self, from: data)
            } catch {
                throw AuthServiceError.malformedResponse
            }

            guard !responseBody.token.isEmpty else {
                throw AuthServiceError.malformedResponse
            }

            return AuthSession(username: username, token: responseBody.token)
        } catch let error as AuthServiceError {
            throw error
        } catch {
            throw AuthServiceError.networkFailure
        }
    }

    private func signInEndpoint(from baseURL: URL) -> URL? {
        guard let scheme = baseURL.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              baseURL.host != nil else {
            return nil
        }

        return baseURL.appendingPathComponent("v1/auth/signin")
    }
}

enum APIConfiguration {
    static var baseURL: URL? {
        guard let rawValue = Bundle.main.object(forInfoDictionaryKey: "API_BASE_URL") as? String else {
            return nil
        }

        let value = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, !value.contains("$(") else {
            return nil
        }

        return URL(string: value)
    }
}

private struct Credentials: Encodable {
    let username: String
    let password: String
}

private struct SignInResponse: Decodable {
    let token: String
}
