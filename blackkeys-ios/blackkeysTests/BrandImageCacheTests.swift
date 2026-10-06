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
