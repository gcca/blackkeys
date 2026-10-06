import SwiftUI

/// Maintenance actions for allowed users (`AppConfiguration.isDebugUser`),
/// opened by long-pressing the username chip in `HomeView`. Nothing here is
/// user-facing product behavior. The sections live in sibling files.
struct DebugView: View {
    private let imageCache: BrandImageCache
    private let brandCache: BrandCaching

    @Environment(\.dismiss) private var dismiss
    /// Bumped after a cache is cleared so sections that show sizes or lists
    /// reload.
    @State private var cacheRevision = 0

    init(imageCache: BrandImageCache = .shared, brandCache: BrandCaching = FileBrandCache()) {
        self.imageCache = imageCache
        self.brandCache = brandCache
    }

    var body: some View {
        NavigationStack {
            List {
                DebugCachesSection(
                    imageCache: imageCache,
                    brandCache: brandCache,
                    revision: cacheRevision,
                    onCacheChange: { cacheRevision += 1 }
                )

                DebugInfoSection(imageCache: imageCache, revision: cacheRevision)
            }
            .navigationTitle("Debug")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

#Preview {
    DebugView()
}
