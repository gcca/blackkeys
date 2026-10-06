import SwiftUI
import UIKit

/// The ws image routes are session-gated, so the request carries the token
/// from `\.brandImageToken`; only a 2xx body is cached, so a 401/404 JSON
/// error never poisons `BrandImageCache`. A `nil` URL (no API base URL) or a
/// failed load (e.g. a brand with no picture → 404) shows the placeholder.
/// For a non-nil URL, `BrandImageCache` is checked *synchronously in init*,
/// not in `.task`/`.onAppear` — that's what lets a cache hit seed `@State`
/// before this view's first `body` call, so the spinner branch is never
/// reached, not even for one frame. See `BrandImageCache.swift`.
struct BrandCardImage: View {
    let url: URL?
    let tint: Color
    @Environment(\.brandImageToken) private var token
    @State private var image: Image?
    @State private var failed = false

    init(url: URL?, tint: Color) {
        self.url = url
        self.tint = tint
        if let url, let data = BrandImageCache.shared.cachedImage(for: url), let uiImage = UIImage(data: data) {
            _image = State(initialValue: Image(uiImage: uiImage))
        }
    }

    var body: some View {
        if let image {
            image
                .resizable()
                .aspectRatio(contentMode: .fill)
        } else if let url, !failed {
            ZStack {
                tint.opacity(0.15)
                ProgressView()
            }
            .task(id: url) {
                var request = URLRequest(url: url)
                if let token {
                    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                }
                guard let (data, response) = try? await URLSession.shared.data(for: request),
                      let http = response as? HTTPURLResponse,
                      (200..<300).contains(http.statusCode),
                      !data.isEmpty,
                      let uiImage = UIImage(data: data) else {
                    failed = true
                    return
                }
                BrandImageCache.shared.store(data, for: url)
                image = Image(uiImage: uiImage)
            }
        } else {
            tint.opacity(0.3)
        }
    }
}

extension EnvironmentValues {
    /// Session token for the ws brand image routes; set by `BrandsView`.
    @Entry var brandImageToken: String?
}

struct FeaturedBrandCard: View {
    let item: BrandPresentation

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            BrandCardImage(url: item.brand.pictureUrl, tint: item.tint)
                .frame(width: 150, height: item.imageHeight)
                .clipped()

            VStack(alignment: .leading, spacing: 2) {
                if let firstTag = item.brand.tags.first {
                    Text(firstTag.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(item.tint)
                }
                Text(item.brand.displayName)
                    .font(.subheadline.weight(.semibold))
            }
            .padding(10)
        }
        .frame(width: 150)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .brandCardBorder()
    }
}

struct BrandFeedCard: View {
    let item: BrandPresentation

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // `.frame(maxWidth: .infinity)` alone doesn't force this image
            // down to the column width: `.aspectRatio(contentMode: .fill)`
            // still reports an ideal size derived from the source photo's
            // own aspect ratio, and `maxWidth` only bounds growth — it
            // won't shrink content below that self-reported ideal. Routing
            // through a tinted backdrop (which has no size opinion of its
            // own and simply reports back whatever width it's proposed)
            // inside an `.overlay`, then reading that resolved width via
            // `GeometryReader`, gives the photo an *exact* frame it can't
            // override.
            item.tint.opacity(0.15)
                .frame(height: item.imageHeight)
                .overlay {
                    GeometryReader { geo in
                        BrandCardImage(url: item.brand.pictureUrl, tint: item.tint)
                            .frame(width: geo.size.width, height: geo.size.height)
                            .clipped()
                    }
                }

            VStack(alignment: .leading, spacing: 4) {
                Text(item.brand.displayName)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(2)

                if !item.secondaryText.isEmpty {
                    Text(item.secondaryText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .padding(10)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .brandCardBorder()
    }
}

extension View {
    /// Thin outline for a brand card. Applied after `clipShape` so it follows
    /// the rounded corners; without it a white card on a white screen has no
    /// visible edge. `strokeBorder` draws inside the shape, so the card's
    /// size doesn't change.
    func brandCardBorder() -> some View {
        overlay {
            RoundedRectangle(cornerRadius: 16)
                .strokeBorder(.separator, lineWidth: 1)
        }
    }
}
