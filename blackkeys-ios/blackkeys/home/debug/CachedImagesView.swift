import SwiftUI

/// Every image on disk with its size, filtered by a plain search field.
struct CachedImagesView: View {
    let imageCache: BrandImageCache
    let revision: Int

    @State private var entries: [CachedImageEntry] = []
    @State private var isLoaded = false
    @State private var query = ""

    var body: some View {
        let visible = entries.matching(query)

        List {
            Section {
                ForEach(visible) { entry in
                    LabeledContent(entry.name, value: Self.sizeText(entry.byteCount))
                        .accessibilityIdentifier("cachedImageRow-\(entry.id)")
                }
            } header: {
                if isLoaded {
                    Text(summary(visibleCount: visible.count))
                }
            }
        }
        .accessibilityIdentifier("cachedImagesList")
        .overlay {
            if isLoaded && visible.isEmpty {
                if entries.isEmpty {
                    ContentUnavailableView("No cached images", systemImage: "photo")
                } else {
                    ContentUnavailableView.search(text: query)
                }
            }
        }
        .navigationTitle("Cached images")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $query)
        .textInputAutocapitalization(.never)
        .autocorrectionDisabled()
        .task(id: revision) {
            // Up to a few hundred files are read; keep that off the main actor.
            entries = await Task.detached { [imageCache] in
                imageCache.cachedImageEntries()
            }.value
            isLoaded = true
        }
    }

    private func summary(visibleCount: Int) -> String {
        let total = Self.sizeText(entries.reduce(0) { $0 + $1.byteCount })
        let noun = entries.count == 1 ? "image" : "images"
        if query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "\(entries.count) \(noun) · \(total)"
        }
        return "\(visibleCount) of \(entries.count) \(noun) · \(total) total"
    }

    private static func sizeText(_ bytes: Int) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }
}
