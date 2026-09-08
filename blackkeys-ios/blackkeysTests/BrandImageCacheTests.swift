import Foundation
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
}
