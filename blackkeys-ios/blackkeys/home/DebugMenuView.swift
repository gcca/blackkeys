import SwiftUI

/// Maintenance actions for allowed users (`AppConfiguration.isDebugUser`),
/// opened by long-pressing the username chip in `HomeView`. Nothing here is
/// user-facing product behavior.
struct DebugMenuView: View {
    private let imageCache: BrandImageCache
    private let brandCache: BrandCaching

    @Environment(\.dismiss) private var dismiss
    @State private var imageCacheBytes = 0
    @State private var message: String?

    init(imageCache: BrandImageCache = .shared, brandCache: BrandCaching = FileBrandCache()) {
        self.imageCache = imageCache
        self.brandCache = brandCache
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Caches") {
                    Button("Clear image cache") {
                        imageCache.removeAll()
                        refreshImageCacheSize()
                        message = "Image cache cleared. Images already on screen stay until their view is rebuilt."
                    }
                    .accessibilityIdentifier("debugMenuClearImagesButton")

                    Button("Clear brands cache") {
                        brandCache.removeAll()
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

                Section("Info") {
                    LabeledContent("API base URL", value: APIConfiguration.baseURL?.absoluteString ?? "Not configured")
                    LabeledContent("Version", value: Self.versionDescription)
                    LabeledContent(
                        "Image cache",
                        value: ByteCountFormatter.string(fromByteCount: Int64(imageCacheBytes), countStyle: .file)
                    )
                }
            }
            .navigationTitle("Debug")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .onAppear(perform: refreshImageCacheSize)
        }
    }

    private func refreshImageCacheSize() {
        imageCacheBytes = imageCache.diskByteCount()
    }

    private static var versionDescription: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return "\(version) (\(build))"
    }
}

#Preview {
    DebugMenuView()
}
