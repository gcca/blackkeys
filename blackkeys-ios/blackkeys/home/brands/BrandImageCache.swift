import Foundation

/// One cached image file, as listed by the debug menu. `name` is the readable
/// part recovered from the file name (e.g. `ADIDAS/picture`).
struct CachedImageEntry: Identifiable, Equatable, Sendable {
    /// The file name on disk; unique because it ends in the URL's hash.
    let id: String
    let name: String
    let byteCount: Int
}

extension Collection where Element == CachedImageEntry {
    /// Entries whose name contains `query`, ignoring case and diacritics. An
    /// empty (or whitespace-only) query keeps everything.
    func matching(_ query: String) -> [CachedImageEntry] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return Array(self) }
        return filter { $0.name.localizedStandardContains(trimmed) }
    }
}

protocol BrandImageCaching: Sendable {
    func loadCachedImage(for url: URL) -> Data?
    func store(_ data: Data, for url: URL)
    func removeAll()
    func byteCount() -> Int
    func entries() -> [CachedImageEntry]
}

/// Stores fetched brand picture/logo bytes under the app's Caches directory,
/// one file per URL, named `<readable label>--<hash of the URL>` (arbitrary
/// query strings/lengths aren't safe filenames, so the hash keeps names
/// unique and the label is percent-encoded and truncated). The label lets the
/// debug menu show which brand an image belongs to. No TTL, unlike
/// `FileBrandCache`'s JSON blob: a brand's photo for a given URL essentially
/// never changes.
final class FileBrandImageCache: BrandImageCaching, @unchecked Sendable {
    /// Older cache directories, deleted by `removeAll()` so clearing the cache
    /// also reclaims their space. `-v2`: images moved to WebP under unchanged
    /// URLs; `-v3`: file names gained the readable label. With no TTL, bytes
    /// cached under an old scheme would otherwise be served (or leaked) forever.
    private static let legacyDirectoryNames = ["BrandImagesCache", "BrandImagesCache-v2"]
    private static let labelLimit = 100
    private static let separator = "--"

    private let root: URL
    private let directory: URL
    private let lock = NSLock()

    init(cacheDirectory: URL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]) {
        self.root = cacheDirectory
        self.directory = cacheDirectory.appendingPathComponent("BrandImagesCache-v3")
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

    func removeAll() {
        lock.lock()
        defer { lock.unlock() }
        try? FileManager.default.removeItem(at: directory)
        for name in Self.legacyDirectoryNames {
            try? FileManager.default.removeItem(at: root.appendingPathComponent(name))
        }
    }

    func byteCount() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return listEntries().reduce(0) { $0 + $1.byteCount }
    }

    /// Sorted by name, case-insensitively.
    func entries() -> [CachedImageEntry] {
        lock.lock()
        defer { lock.unlock() }
        return listEntries()
    }

    private func listEntries() -> [CachedImageEntry] {
        let files = (try? FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.fileSizeKey]
        )) ?? []
        return files
            .map { file in
                CachedImageEntry(
                    id: file.lastPathComponent,
                    name: Self.displayName(fromFileName: file.lastPathComponent),
                    byteCount: (try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
                )
            }
            .sorted {
                let order = $0.name.localizedCaseInsensitiveCompare($1.name)
                return order == .orderedSame ? $0.id < $1.id : order == .orderedAscending
            }
    }

    private func fileURL(for url: URL) -> URL {
        directory.appendingPathComponent(Self.fileName(for: url))
    }

    static func fileName(for url: URL) -> String {
        Self.encodedLabel(for: url) + separator + Self.hash(of: url)
    }

    /// Splits at the last separator (a label may itself contain `--`) and
    /// undoes the percent-encoding. Text that isn't valid percent-encoding is
    /// shown as is.
    static func displayName(fromFileName fileName: String) -> String {
        let label: String
        if let range = fileName.range(of: separator, options: .backwards) {
            label = String(fileName[..<range.lowerBound])
        } else {
            label = fileName
        }
        return label.removingPercentEncoding ?? label
    }

    /// `…/v1/brands/<name>/<kind>` reads as `<name>/<kind>`. Any other URL
    /// falls back to its last path component, then its host.
    private static func label(for url: URL) -> String {
        let components = (URLComponents(url: url, resolvingAgainstBaseURL: false)?.percentEncodedPath ?? "")
            .split(separator: "/", omittingEmptySubsequences: true)
            .map { String($0).removingPercentEncoding ?? String($0) }

        if components.count > 2, components[0] == "v1", components[1] == "brands" {
            return components.dropFirst(2).joined(separator: "/")
        }
        return components.last ?? url.host ?? "image"
    }

    private static let unreserved = CharacterSet(
        charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    )

    /// Encodes one character at a time and stops before the limit, so a
    /// truncated label never ends in half a percent-escape.
    private static func encodedLabel(for url: URL) -> String {
        var encoded = ""
        for character in label(for: url) {
            let piece = String(character).addingPercentEncoding(withAllowedCharacters: unreserved) ?? ""
            guard encoded.utf8.count + piece.utf8.count <= labelLimit else { break }
            encoded += piece
        }
        return encoded.isEmpty ? "image" : encoded
    }

    /// FNV-1a over the URL string, not `String.hashValue` — Swift's hash is
    /// randomly reseeded per process launch, so it can't give a filename
    /// stable across app runs (same reasoning as `BrandPresentation.seededIndex`).
    private static func hash(of url: URL) -> String {
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

    /// Drops both layers. Views already showing an image keep it until they
    /// are rebuilt; the next load of any URL goes back to the network.
    func removeAll() {
        memory.removeAllObjects()
        disk.removeAll()
    }

    func diskByteCount() -> Int {
        disk.byteCount()
    }

    /// What is on disk (the memory layer only mirrors it), sorted by name.
    func cachedImageEntries() -> [CachedImageEntry] {
        disk.entries()
    }
}
