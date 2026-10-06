import SwiftUI

/// Clear buttons for both caches, plus the way into the cached-images list.
struct DebugCachesSection: View {
    let imageCache: BrandImageCache
    let brandCache: BrandCaching
    let revision: Int
    let onCacheChange: () -> Void

    @State private var message: String?

    var body: some View {
        Section("Caches") {
            NavigationLink("Cached images") {
                CachedImagesView(imageCache: imageCache, revision: revision)
            }
            .accessibilityIdentifier("debugCachedImagesLink")

            Button("Clear image cache") {
                imageCache.removeAll()
                onCacheChange()
                message = "Image cache cleared. Images already on screen stay until their view is rebuilt."
            }
            .accessibilityIdentifier("debugMenuClearImagesButton")

            Button("Clear brands cache") {
                brandCache.removeAll()
                onCacheChange()
                message = "Brands cache cleared. The list is fetched again on the next launch or Retry."
            }
            .accessibilityIdentifier("debugMenuClearBrandsButton")

            if let message {
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("debugMenuMessage")
            }
        }
    }
}
