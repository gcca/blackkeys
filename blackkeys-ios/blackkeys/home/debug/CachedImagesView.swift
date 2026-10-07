import SwiftUI

/// Every image on disk (pictures and logos alike) with its metadata, filtered by kind and a search field.
struct CachedImagesView: View {
    let imageCache: BrandImageCache
    let revision: Int

    @State private var entries: [CachedImageEntry] = []
    @State private var isLoaded = false
    @State private var query = ""
    @State private var kind: CachedImageKind?

    var body: some View {
        let visible = entries.filter { kind == nil || $0.kind == kind }.matching(query)

        List {
            Section {
                Picker("Kind", selection: $kind) {
                    Text("All").tag(CachedImageKind?.none)
                    Text("Pictures").tag(CachedImageKind?.some(.picture))
                    Text("Logos").tag(CachedImageKind?.some(.logo))
                }
                .pickerStyle(.segmented)
                .accessibilityIdentifier("cachedImagesKindPicker")
            }

            Section {
                ForEach(visible) { entry in
                    row(for: entry)
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

    private func row(for entry: CachedImageEntry) -> some View {
        let dimensions = entry.pixelWidth.flatMap { width in
            entry.pixelHeight.map { "\(width)×\($0) px" }
        }
        let updated = entry.modified?.formatted(date: .abbreviated, time: .shortened)
        return VStack(alignment: .leading, spacing: 2) {
            Text(entry.name)
            Group {
                Text("\(Self.sizeText(entry.byteCount)) (\(entry.byteCount.formatted()) bytes)")
                Text("\(dimensions ?? "—") · ratio \(entry.aspectRatio ?? "—") · \(entry.format ?? "—")")
                Text("Updated \(updated ?? "—")")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
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
