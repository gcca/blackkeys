import Foundation

protocol BrandImageCaching: Sendable {
    func loadCachedImage(for url: URL) -> Data?
    func store(_ data: Data, for url: URL)
}

/// Stores fetched brand picture/logo bytes under the app's Caches directory,
/// one file per URL (named by a stable hash of the URL — arbitrary query
/// strings/lengths aren't safe filenames). No TTL, unlike `FileBrandCache`'s
/// JSON blob: a brand's photo for a given URL essentially never changes.
final class FileBrandImageCache: BrandImageCaching, @unchecked Sendable {
    private let directory: URL
    private let lock = NSLock()

    init(cacheDirectory: URL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]) {
        self.directory = cacheDirectory.appendingPathComponent("BrandImagesCache")
    }

    func loadCachedImage(for url: URL) -> Data? {
        lock.lock()
        defer { lock.unlock() }
        return try? Data(contentsOf: fileURL(for: url))
    }

    func store(_ data: Data, for url: URL) {
        lock.lock()
        defer { lock.unlock() }
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try? data.write(to: fileURL(for: url), options: .atomic)
    }

    private func fileURL(for url: URL) -> URL {
        directory.appendingPathComponent(Self.fileName(for: url))
    }

    /// FNV-1a over the URL string, not `String.hashValue` — Swift's hash is
    /// randomly reseeded per process launch, so it can't give a filename
    /// stable across app runs (same reasoning as `BrandPresentation.seededIndex`).
    private static func fileName(for url: URL) -> String {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for byte in url.absoluteString.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x0000_0100_0000_01b3
        }
        return String(hash, radix: 16)
    }
}

/// In-memory front for `FileBrandImageCache`: avoids a disk read for a URL
/// already seen this process launch. `NSCache` is thread-safe on its own.
final class BrandImageCache: @unchecked Sendable {
    static let shared = BrandImageCache()

    private let memory = NSCache<NSURL, NSData>()
    private let disk: BrandImageCaching

    init(disk: BrandImageCaching = FileBrandImageCache()) {
        self.disk = disk
    }

    /// Synchronous by design — called from `BrandCardImage.init` so a cache
    /// hit can render on the view's very first frame, with no loading flash.
    func cachedImage(for url: URL) -> Data? {
        if let cached = memory.object(forKey: url as NSURL) {
            return cached as Data
        }
        guard let data = disk.loadCachedImage(for: url) else { return nil }
        memory.setObject(data as NSData, forKey: url as NSURL)
        return data
    }

    func store(_ data: Data, for url: URL) {
        memory.setObject(data as NSData, forKey: url as NSURL)
        disk.store(data, for: url)
    }
}
