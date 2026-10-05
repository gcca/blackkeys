import Foundation

struct Brand: Codable, Identifiable, Equatable, Sendable {
    var id: String { name }
    let name: String
    let displayName: String
    let description: String
    let isActive: Bool
    let kioskId: Int
    let amenities: [Amenity]
    let stores: [Store]
    let tags: [String]

    struct Amenity: Codable, Equatable, Sendable {
        let name: String
        let value: String
    }

    struct Store: Codable, Equatable, Sendable {
        let id: Int
        let name: String
    }

    /// Served by ws (`GET v1/brands/<name>/logo|picture`, session-gated —
    /// `BrandCardImage` attaches the token) rather than carried in the list
    /// payload. `nil` when the build has no API base URL configured.
    var logoUrl: URL? { imageURL(kind: "logo") }
    var pictureUrl: URL? { imageURL(kind: "picture") }

    /// `name` is percent-encoded as a single path segment: `/` is escaped
    /// too, so an odd name can't split the route that ws matches on.
    func imageURL(kind: String, baseURL: URL? = APIConfiguration.baseURL) -> URL? {
        var allowed = CharacterSet.urlPathAllowed
        allowed.remove("/")
        guard let baseURL,
              let scheme = baseURL.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              baseURL.host != nil,
              let segment = name.addingPercentEncoding(withAllowedCharacters: allowed) else {
            return nil
        }
        return URL(string: baseURL.absoluteString.trimmingSuffix("/") + "/v1/brands/" + segment + "/" + kind)
    }
}

private extension String {
    func trimmingSuffix(_ suffix: String) -> String {
        hasSuffix(suffix) ? String(dropLast(suffix.count)) : self
    }
}

enum BrandServiceError: Error, Equatable, LocalizedError, Sendable {
    case invalidConfiguration
    case sessionExpired
    case serviceUnavailable
    case malformedResponse
    case networkFailure

    var errorDescription: String? {
        switch self {
        case .invalidConfiguration:
            "Brands are not configured for this build."
        case .sessionExpired:
            "Your session has expired. Please sign in again."
        case .serviceUnavailable:
            "The brands service is temporarily unavailable."
        case .malformedResponse:
            "The brands service returned an unexpected response."
        case .networkFailure:
            "Unable to reach the brands service. Please try again."
        }
    }
}

struct BrandsCacheEntry: Codable, Equatable, Sendable {
    let brands: [Brand]
    let fetchedAt: Date
}

protocol BrandCaching: Sendable {
    func loadCachedBrands() -> BrandsCacheEntry?
    func store(_ entry: BrandsCacheEntry)
}

/// Stores the fetched brand list as a single JSON file under the app's
/// Caches directory. `Caches` (not `UserDefaults`) is the right place for
/// this: it's regenerable, disposable data the OS may purge under storage
/// pressure, unlike the small plist-serializable preferences `UserDefaults`
/// is meant for. Worst case on purge is one extra network round trip.
final class FileBrandCache: BrandCaching, @unchecked Sendable {
    private let fileURL: URL
    private let lock = NSLock()

    init(cacheDirectory: URL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]) {
        self.fileURL = cacheDirectory.appendingPathComponent("BrandsCache/brands.json")
    }

    func loadCachedBrands() -> BrandsCacheEntry? {
        lock.lock()
        defer { lock.unlock() }

        guard let data = try? Data(contentsOf: fileURL) else {
            return nil
        }
        return try? JSONDecoder().decode(BrandsCacheEntry.self, from: data)
    }

    func store(_ entry: BrandsCacheEntry) {
        lock.lock()
        defer { lock.unlock() }

        guard let data = try? JSONEncoder().encode(entry) else {
            return
        }

        let directory = fileURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try? data.write(to: fileURL, options: .atomic)
    }
}

struct BrandService: Sendable {
    private static let cacheTTL: TimeInterval = AppConfiguration.brandsCacheTTLSeconds

    private let baseURL: URL?
    private let session: URLSession
    private let cache: BrandCaching

    init(
        baseURL: URL? = APIConfiguration.baseURL,
        session: URLSession = .shared,
        cache: BrandCaching = FileBrandCache()
    ) {
        self.baseURL = baseURL
        self.session = session
        self.cache = cache
    }

    func fetchBrands(token: String) async throws -> [Brand] {
        if let cached = cache.loadCachedBrands(), isFresh(cached) {
            return cached.brands
        }

        do {
            let brands = try await fetchFromNetwork(token: token)
            cache.store(BrandsCacheEntry(brands: brands, fetchedAt: Date()))
            return brands
        } catch BrandServiceError.networkFailure {
            if let cached = cache.loadCachedBrands() {
                return cached.brands
            }
            throw BrandServiceError.networkFailure
        } catch BrandServiceError.serviceUnavailable {
            if let cached = cache.loadCachedBrands() {
                return cached.brands
            }
            throw BrandServiceError.serviceUnavailable
        }
    }

    private func isFresh(_ entry: BrandsCacheEntry) -> Bool {
        Date().timeIntervalSince(entry.fetchedAt) < Self.cacheTTL
    }

    private func fetchFromNetwork(token: String) async throws -> [Brand] {
        guard let baseURL, let endpoint = brandsListEndpoint(from: baseURL) else {
            throw BrandServiceError.invalidConfiguration
        }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        do {
            let (data, response) = try await session.data(for: request)
            guard let response = response as? HTTPURLResponse else {
                throw BrandServiceError.malformedResponse
            }

            switch response.statusCode {
            case 200 ... 299:
                break
            case 401:
                throw BrandServiceError.sessionExpired
            case 503:
                throw BrandServiceError.serviceUnavailable
            default:
                throw BrandServiceError.malformedResponse
            }

            do {
                return try JSONDecoder().decode([Brand].self, from: data)
            } catch {
                throw BrandServiceError.malformedResponse
            }
        } catch let error as BrandServiceError {
            throw error
        } catch {
            throw BrandServiceError.networkFailure
        }
    }

    private func brandsListEndpoint(from baseURL: URL) -> URL? {
        guard let scheme = baseURL.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              baseURL.host != nil else {
            return nil
        }

        return baseURL.appendingPathComponent("v1/brands/list")
    }
}
