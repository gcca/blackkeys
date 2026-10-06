import Foundation
import UIKit
import Testing
@testable import blackkeys

@Suite
struct FileBrandImageCacheTests {
    @Test func roundTripsImageDataThroughAScratchDirectory() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandImageCache(cacheDirectory: scratch)
        let url = URL(string: "https://example/picture.jpg")!
        let data = Data([0xFF, 0xD8, 0xFF, 0xD9])

        #expect(cache.loadCachedImage(for: url) == nil)
        cache.store(data, for: url)
        #expect(cache.loadCachedImage(for: url) == data)
    }

    @Test func differentURLsDoNotCollideOnDisk() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandImageCache(cacheDirectory: scratch)
        let a = URL(string: "https://example/a.jpg")!
        let b = URL(string: "https://example/b.jpg")!

        cache.store(Data([0x01]), for: a)
        cache.store(Data([0x02]), for: b)

        #expect(cache.loadCachedImage(for: a) == Data([0x01]))
        #expect(cache.loadCachedImage(for: b) == Data([0x02]))
    }

    @Test func removeAllEmptiesTheDirectoryAndTheCacheStaysUsable() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandImageCache(cacheDirectory: scratch)
        let a = URL(string: "https://example/a.jpg")!
        let b = URL(string: "https://example/b.jpg")!

        #expect(cache.byteCount() == 0)
        cache.store(Data([0x01, 0x02, 0x03]), for: a)
        cache.store(Data([0x04, 0x05]), for: b)
        #expect(cache.byteCount() == 5)

        cache.removeAll()
        #expect(cache.loadCachedImage(for: a) == nil)
        #expect(cache.loadCachedImage(for: b) == nil)
        #expect(cache.byteCount() == 0)

        cache.removeAll()
        cache.store(Data([0x09]), for: a)
        #expect(cache.loadCachedImage(for: a) == Data([0x09]))
    }

    @Test func memoryFrontDropsEntriesToo() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = BrandImageCache(disk: FileBrandImageCache(cacheDirectory: scratch))
        let url = URL(string: "https://example/a.jpg")!

        cache.store(Data([0x01]), for: url)
        #expect(cache.cachedImage(for: url) == Data([0x01]))

        cache.removeAll()
        #expect(cache.cachedImage(for: url) == nil)
        #expect(cache.diskByteCount() == 0)
    }

    /// The ws image routes serve `image/webp`; `BrandCardImage` decodes
    /// cached and fetched bytes with `UIImage(data:)`.
    @Test func cachedWebPDataDecodesAsAnImage() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandImageCache(cacheDirectory: scratch)
        let url = URL(string: "https://example/v1/brands/acme/picture")!
        // 1×1 lossless WebP.
        let webp = try #require(Data(base64Encoded: "UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA=="))

        cache.store(webp, for: url)
        let data = try #require(cache.loadCachedImage(for: url))
        let image = try #require(UIImage(data: data))
        #expect(image.size == CGSize(width: 1, height: 1))
    }
}

@Suite
struct CachedImageListingTests {
    @Test func listsNamesAndSizesSortedByNameIgnoringCase() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandImageCache(cacheDirectory: scratch)

        cache.store(Data([0x01]), for: try imageURL(brand: "bcp", kind: "picture"))
        cache.store(Data([0x01, 0x02, 0x03]), for: try imageURL(brand: "ADIDAS", kind: "picture"))
        cache.store(Data([0x01, 0x02]), for: try imageURL(brand: "ADIDAS", kind: "logo"))

        let entries = cache.entries()
        #expect(entries.map(\.name) == ["ADIDAS/logo", "ADIDAS/picture", "bcp/picture"])
        #expect(entries.map(\.byteCount) == [2, 3, 1])
        #expect(Set(entries.map(\.id)).count == 3)
    }

    @Test func aMissingDirectoryHasNoEntries() {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)

        #expect(FileBrandImageCache(cacheDirectory: scratch).entries().isEmpty)
    }

    @Test func namesWithSpacesAccentsSlashesAndSeparatorsRoundTrip() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandImageCache(cacheDirectory: scratch)
        let brands = ["Café & Co", "A/B", "a--b", "100% Pura"]

        for brand in brands {
            let url = try imageURL(brand: brand, kind: "picture")
            cache.store(Data([0x07]), for: url)
            #expect(cache.loadCachedImage(for: url) == Data([0x07]))
        }

        let names = Set(cache.entries().map(\.name))
        #expect(names == Set(brands.map { "\($0)/picture" }))
    }

    @Test func aVeryLongNameStaysAValidFilenameAndStillLoads() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandImageCache(cacheDirectory: scratch)
        let url = try imageURL(brand: String(repeating: "ñ", count: 300), kind: "logo")

        cache.store(Data([0x05]), for: url)

        #expect(cache.loadCachedImage(for: url) == Data([0x05]))
        let entry = try #require(cache.entries().first)
        #expect(entry.id.utf8.count < 255)
        #expect(entry.name.hasPrefix("ñññ"))
        #expect(entry.name.allSatisfy { $0 == "ñ" })
    }

    @Test func otherURLsFallBackToTheLastPathComponentThenTheHost() throws {
        #expect(FileBrandImageCache.displayName(
            fromFileName: FileBrandImageCache.fileName(for: URL(string: "https://example.com/assets/logo.png")!)
        ) == "logo.png")
        #expect(FileBrandImageCache.displayName(
            fromFileName: FileBrandImageCache.fileName(for: URL(string: "https://example.com")!)
        ) == "example.com")
    }

    @Test func urlsWithTheSameLabelStayDistinctOnDisk() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let cache = FileBrandImageCache(cacheDirectory: scratch)
        let a = URL(string: "https://a.example/x/logo.png")!
        let b = URL(string: "https://b.example/y/logo.png")!

        cache.store(Data([0x01]), for: a)
        cache.store(Data([0x02]), for: b)

        #expect(cache.entries().map(\.name) == ["logo.png", "logo.png"])
        #expect(cache.loadCachedImage(for: a) == Data([0x01]))
        #expect(cache.loadCachedImage(for: b) == Data([0x02]))
    }

    @Test func aFileWithoutTheSeparatorShowsItsRawName() {
        #expect(FileBrandImageCache.displayName(fromFileName: "legacyhash") == "legacyhash")
    }

    @Test func removeAllAlsoDeletesLegacyCacheDirectories() throws {
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let legacy = ["BrandImagesCache", "BrandImagesCache-v2"].map { scratch.appendingPathComponent($0) }
        for directory in legacy {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try Data([0x01]).write(to: directory.appendingPathComponent("old"))
        }
        let cache = FileBrandImageCache(cacheDirectory: scratch)
        cache.store(Data([0x02]), for: try imageURL(brand: "acme", kind: "logo"))

        cache.removeAll()

        for directory in legacy {
            #expect(!FileManager.default.fileExists(atPath: directory.path))
        }
        #expect(cache.entries().isEmpty)
    }
}

@Suite
struct CachedImageFilterTests {
    private let entries = [
        CachedImageEntry(id: "1", name: "ADIDAS/logo", byteCount: 1),
        CachedImageEntry(id: "2", name: "Café Central/picture", byteCount: 2),
        CachedImageEntry(id: "3", name: "bcp/picture", byteCount: 3),
    ]

    @Test func anEmptyOrBlankQueryKeepsEverything() {
        #expect(entries.matching("") == entries)
        #expect(entries.matching("  \n") == entries)
    }

    @Test func matchesIgnoringCase() {
        #expect(entries.matching("adidas").map(\.id) == ["1"])
        #expect(entries.matching("PICTURE").map(\.id) == ["2", "3"])
    }

    @Test func matchesIgnoringDiacritics() {
        #expect(entries.matching("cafe").map(\.id) == ["2"])
    }

    @Test func trimsTheQuery() {
        #expect(entries.matching("  bcp ").map(\.id) == ["3"])
    }

    @Test func noMatchGivesAnEmptyList() {
        #expect(entries.matching("zzz").isEmpty)
    }
}

private func imageURL(brand: String, kind: String) throws -> URL {
    let model = Brand(
        name: brand,
        displayName: brand,
        description: "",
        isActive: true,
        kioskId: 1,
        amenities: [],
        stores: [],
        tags: []
    )
    return try #require(model.imageURL(kind: kind, baseURL: URL(string: "https://ws.example")))
}
