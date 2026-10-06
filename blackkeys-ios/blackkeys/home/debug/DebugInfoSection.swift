import SwiftUI

/// Read-only facts about this build and its image cache.
struct DebugInfoSection: View {
    let imageCache: BrandImageCache
    let revision: Int

    @State private var imageCacheBytes = 0

    var body: some View {
        Section("Info") {
            LabeledContent("API base URL", value: APIConfiguration.baseURL?.absoluteString ?? "Not configured")
            LabeledContent("Version", value: Self.versionDescription)
            LabeledContent(
                "Image cache",
                value: ByteCountFormatter.string(fromByteCount: Int64(imageCacheBytes), countStyle: .file)
            )
        }
        .task(id: revision) {
            imageCacheBytes = imageCache.diskByteCount()
        }
    }

    private static var versionDescription: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return "\(version) (\(build))"
    }
}
