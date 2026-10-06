import Foundation
import Testing
@testable import blackkeys

@Suite(.serialized)
struct BrandServiceTests {
    @Test func fetchSendsExpectedRequestAndDecodesBrands() async throws {
        let cache = InMemoryBrandCache()
        let session = makeSession { request in
            StubBrandURLProtocol.recordedRequest = request
            return response(statusCode: 200, body: sampleBrandsJSON)
        }
        let service = BrandService(baseURL: URL(string: "https://api.example.com")!, session: session, cache: cache)

        let brands = try await service.fetchBrands(token: "blackkeys-v1_abc")

        #expect(brands.count == 1)
        let brand = try #require(brands.first)
        #expect(brand.name == "ADIDAS")
        #expect(brand.displayName == "Adidas")
        #expect(brand.description == "desc")
        #expect(brand.isActive == true)
        #expect(brand.kioskId == 12)
        #expect(brand.amenities == [Brand.Amenity(name: "wifi", value: "yes")])
        #expect(brand.stores == [Brand.Store(id: 4, name: "Corredor Mantaro, 2do nivel")])
        #expect(brand.tags == ["sports", "outdoor"])

        let request = try #require(StubBrandURLProtocol.recordedRequest)
        #expect(request.httpMethod == "GET")
        #expect(request.url == URL(string: "https://api.example.com/v1/brands/list"))
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer blackkeys-v1_abc")
    }

    @Test func imageURLsPointAtTheWsBrandImageRoutes() {
        let baseURL = URL(string: "https://api.example.com")!
        #expect(sampleBrand.imageURL(kind: "logo", baseURL: baseURL) == URL(string: "https://api.example.com/v1/brands/ADIDAS/logo"))
        #expect(sampleBrand.imageURL(kind: "picture", baseURL: baseURL) == URL(string: "https://api.example.com/v1/brands/ADIDAS/picture"))
    }

    @Test func imageURLEscapesTheNameAsASinglePathSegment() {
        let brand = Brand(
            name: "a/b c", displayName: "", description: "", isActive: true,
            kioskId: 0, amenities: [], stores: [], tags: []
        )
        let url = brand.imageURL(kind: "logo", baseURL: URL(string: "https://api.example.com/")!)
        #expect(url?.absoluteString == "https://api.example.com/v1/brands/a%2Fb%20c/logo")
    }

    @Test func imageURLIsNilWithoutAUsableBaseURL() {
        #expect(sampleBrand.imageURL(kind: "logo", baseURL: nil) == nil)
        #expect(sampleBrand.imageURL(kind: "logo", baseURL: URL(string: "ftp://api.example.com")!) == nil)
    }

    @Test func missingBaseURLIsAConfigurationError() async {
        let service = BrandService(baseURL: nil, session: makeSession { _ in
            response(statusCode: 200, body: "[]")
        }, cache: InMemoryBrandCache())

        await expect(.invalidConfiguration, from: service)
    }

    @Test func unauthorizedIsMappedToSessionExpired() async {
        await expectStatus(401, as: .sessionExpired, cache: InMemoryBrandCache())
    }

    @Test func serviceUnavailableWithNoCacheThrows() async {
        await expectStatus(503, as: .serviceUnavailable, cache: InMemoryBrandCache())
    }

    @Test func malformedBodyIsMappedToMalformedResponse() async {
        let service = BrandService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in response(statusCode: 200, body: "not json") },
            cache: InMemoryBrandCache()
        )

        await expect(.malformedResponse, from: service)
    }

    @Test func unexpectedStatusIsMappedToMalformedResponse() async {
        await expectStatus(500, as: .malformedResponse, cache: InMemoryBrandCache())
    }

    @Test func transportFailureWithNoCacheIsMappedToNetworkFailure() async {
        let service = BrandService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in throw URLError(.notConnectedToInternet) },
            cache: InMemoryBrandCache()
        )

        await expect(.networkFailure, from: service)
    }

    @Test func freshCacheSkipsTheNetwork() async throws {
        let cache = InMemoryBrandCache()
        cache.entry = BrandsCacheEntry(brands: [sampleBrand], fetchedAt: Date())
        StubBrandURLProtocol.recordedRequest = nil
        let service = BrandService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in response(statusCode: 200, body: "[]") },
            cache: cache
        )

        let brands = try await service.fetchBrands(token: "t")

        #expect(brands == [sampleBrand])
        #expect(StubBrandURLProtocol.recordedRequest == nil)
    }

    @Test func staleCacheTriggersANetworkFetchAndRewritesTheCache() async throws {
        let cache = InMemoryBrandCache()
        cache.entry = BrandsCacheEntry(brands: [sampleBrand], fetchedAt: Date().addingTimeInterval(-25 * 60 * 60))
        let session = makeSession { request in
            StubBrandURLProtocol.recordedRequest = request
            return response(statusCode: 200, body: sampleBrandsJSON)
        }
        let service = BrandService(baseURL: URL(string: "https://api.example.com")!, session: session, cache: cache)

        _ = try await service.fetchBrands(token: "t")

        #expect(StubBrandURLProtocol.recordedRequest != nil)
        let stored = try #require(cache.entry)
        #expect(stored.brands.first?.name == "ADIDAS")
    }

    @Test func successfulFetchPopulatesTheCache() async throws {
        let cache = InMemoryBrandCache()
        let service = BrandService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in response(statusCode: 200, body: sampleBrandsJSON) },
            cache: cache
        )

        _ = try await service.fetchBrands(token: "t")

        let stored = try #require(cache.entry)
        #expect(stored.brands.first?.name == "ADIDAS")
    }

    @Test func networkFailureFallsBackToAnExistingCache() async throws {
        let cache = InMemoryBrandCache()
        cache.entry = BrandsCacheEntry(brands: [sampleBrand], fetchedAt: Date().addingTimeInterval(-25 * 60 * 60))
        let service = BrandService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in throw URLError(.notConnectedToInternet) },
            cache: cache
        )

        let brands = try await service.fetchBrands(token: "t")

        #expect(brands == [sampleBrand])
    }

    @Test func serviceUnavailableFallsBackToAnExistingCache() async throws {
        let cache = InMemoryBrandCache()
        cache.entry = BrandsCacheEntry(brands: [sampleBrand], fetchedAt: Date().addingTimeInterval(-25 * 60 * 60))

        let brands = try await BrandService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in response(statusCode: 503, body: "{}") },
            cache: cache
        ).fetchBrands(token: "t")

        #expect(brands == [sampleBrand])
    }

    @Test func sessionExpiredIsNotMaskedByAnExistingCache() async {
        let cache = InMemoryBrandCache()
        cache.entry = BrandsCacheEntry(brands: [sampleBrand], fetchedAt: Date().addingTimeInterval(-25 * 60 * 60))

        await expectStatus(401, as: .sessionExpired, cache: cache)
    }

    @Test func malformedResponseIsNotMaskedByAnExistingCache() async {
        let cache = InMemoryBrandCache()
        cache.entry = BrandsCacheEntry(brands: [sampleBrand], fetchedAt: Date().addingTimeInterval(-25 * 60 * 60))

        let service = BrandService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in response(statusCode: 200, body: "not json") },
            cache: cache
        )

        await expect(.malformedResponse, from: service)
    }

    @Test func invalidConfigurationIsNotMaskedByAnExistingCache() async {
        let cache = InMemoryBrandCache()
        cache.entry = BrandsCacheEntry(brands: [sampleBrand], fetchedAt: Date().addingTimeInterval(-25 * 60 * 60))
        let service = BrandService(baseURL: nil, session: makeSession { _ in response(statusCode: 200, body: "[]") }, cache: cache)

        await expect(.invalidConfiguration, from: service)
    }

    private func expectStatus(_ statusCode: Int, as expectedError: BrandServiceError, cache: BrandCaching) async {
        let service = BrandService(
            baseURL: URL(string: "https://api.example.com")!,
            session: makeSession { _ in response(statusCode: statusCode, body: "{}") },
            cache: cache
        )

        await expect(expectedError, from: service)
    }

    private func expect(_ expectedError: BrandServiceError, from service: BrandService) async {
        do {
            _ = try await service.fetchBrands(token: "t")
            Issue.record("Expected \(expectedError) to be thrown")
        } catch let error as BrandServiceError {
            #expect(error == expectedError)
        } catch {
            Issue.record("Expected BrandServiceError, got \(error)")
        }
    }
}

@Suite
struct FileBrandCacheTests {
    @Test func roundTripsAnEntryThroughAScratchDirectory() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandCache(cacheDirectory: scratch)
        let entry = BrandsCacheEntry(brands: [sampleBrand], fetchedAt: Date())

        #expect(cache.loadCachedBrands() == nil)

        cache.store(entry)

        let loaded = try #require(cache.loadCachedBrands())
        #expect(loaded.brands == entry.brands)
        #expect(abs(loaded.fetchedAt.timeIntervalSince(entry.fetchedAt)) < 1)
    }

    @Test func removeAllDropsTheEntryAndTheCacheStaysUsable() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandCache(cacheDirectory: scratch)
        let entry = BrandsCacheEntry(brands: [sampleBrand], fetchedAt: Date())

        cache.store(entry)
        cache.removeAll()
        #expect(cache.loadCachedBrands() == nil)

        cache.removeAll()
        cache.store(entry)
        #expect(cache.loadCachedBrands()?.brands == entry.brands)
    }
}

private let sampleBrand = Brand(
    name: "ADIDAS",
    displayName: "Adidas",
    description: "desc",
    isActive: true,
    kioskId: 12,
    amenities: [Brand.Amenity(name: "wifi", value: "yes")],
    stores: [Brand.Store(id: 4, name: "Corredor Mantaro, 2do nivel")],
    tags: ["sports", "outdoor"]
)

private let sampleBrandsJSON = """
[
    {
        "name": "ADIDAS",
        "displayName": "Adidas",
        "description": "desc",
        "isActive": true,
        "kioskId": 12,
        "amenities": [{"name": "wifi", "value": "yes"}],
        "stores": [{"id": 4, "name": "Corredor Mantaro, 2do nivel"}],
        "tags": ["sports", "outdoor"]
    }
]
"""

private final class InMemoryBrandCache: BrandCaching, @unchecked Sendable {
    var entry: BrandsCacheEntry?

    func loadCachedBrands() -> BrandsCacheEntry? {
        entry
    }

    func store(_ entry: BrandsCacheEntry) {
        self.entry = entry
    }

    func removeAll() {
        entry = nil
    }
}

private func makeSession(
    handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
) -> URLSession {
    StubBrandURLProtocol.handler = handler
    StubBrandURLProtocol.recordedRequest = nil

    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [StubBrandURLProtocol.self]
    return URLSession(configuration: configuration)
}

private func response(statusCode: Int, body: String) -> (HTTPURLResponse, Data) {
    let url = URL(string: "https://api.example.com/v1/brands/list")!
    return (HTTPURLResponse(url: url, statusCode: statusCode, httpVersion: nil, headerFields: nil)!, Data(body.utf8))
}

private final class StubBrandURLProtocol: URLProtocol, @unchecked Sendable {
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
