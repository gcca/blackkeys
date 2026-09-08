import SwiftUI

struct BrandsView: View {
    private enum LoadState {
        case loading
        case loaded
        case failed(BrandServiceError)
    }

    private let token: String?
    private let brandService: BrandService
    private let topContentInset: CGFloat
    private let onScrollDepthChange: (CGFloat) -> Void

    @State private var brands: [Brand] = []
    @State private var loadState: LoadState = .loading
    @State private var selectedBrand: Brand?

    init(
        token: String? = nil,
        brandService: BrandService = BrandService(),
        topContentInset: CGFloat = 12,
        onScrollDepthChange: @escaping (CGFloat) -> Void = { _ in }
    ) {
        self.token = token
        self.brandService = brandService
        self.topContentInset = topContentInset
        self.onScrollDepthChange = onScrollDepthChange
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                heroBanner
                    .padding(.horizontal)

                switch loadState {
                case .loading:
                    BrandsLoadingView()
                case .failed(let error):
                    BrandsErrorView(error: error) {
                        Task { await loadBrands() }
                    }
                case .loaded:
                    featuredSection

                    sectionIntro

                    feedGrid
                }
            }
            .padding(.top, topContentInset)
        }
        .onScrollGeometryChange(for: CGFloat.self) { geometry in
            max(0, geometry.contentOffset.y + geometry.contentInsets.top)
        } action: { oldValue, newValue in
            guard oldValue != newValue else { return }
            onScrollDepthChange(newValue)
        }
        .task(id: token) {
            await loadBrands()
        }
        .sheet(item: $selectedBrand) { brand in
            BrandView(item: BrandPresentation(brand: brand))
        }
    }

    private func loadBrands() async {
        guard let token else {
            loadState = .failed(.sessionExpired)
            return
        }

        loadState = .loading
        do {
            brands = try await brandService.fetchBrands(token: token)
            loadState = .loaded
        } catch let error as BrandServiceError {
            loadState = .failed(error)
        } catch {
            loadState = .failed(.networkFailure)
        }
    }

    /// Decorative banner built from the mall's own 4 brand colors (sampled
    /// from its official logo) rather than a photo — avoids sourcing a
    /// photo of unclear license just for a background element.
    private var heroBanner: some View {
        RoundedRectangle(cornerRadius: 20)
            .fill(
                LinearGradient(
                    colors: [
                        Color(red: 0x1b / 255, green: 0x44 / 255, blue: 0x9c / 255),
                        Color(red: 0x96 / 255, green: 0x3d / 255, blue: 0x97 / 255),
                        Color(red: 0x00 / 255, green: 0x82 / 255, blue: 0x86 / 255),
                        Color(red: 0xf5 / 255, green: 0x82 / 255, blue: 0x2b / 255),
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .frame(height: 160)
    }

    private var sectionIntro: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("DIRECTORY")
                .font(.caption.weight(.bold))
                .tracking(1)
                .foregroundStyle(Color.accentColor)
            Text("Find your store")
                .font(.largeTitle.bold())
        }
        .padding(.horizontal)
    }

    /// Two-column masonry feed: unlike `LazyVGrid`, cards aren't locked into
    /// shared row heights — each column accumulates independently, so a short
    /// card and a tall card can sit side-by-side without a gap.
    private var feedGrid: some View {
        MasonryLayout(horizontalSpacing: 12, verticalSpacing: 12) {
            ForEach(brands) { brand in
                Button {
                    selectedBrand = brand
                } label: {
                    BrandFeedCard(item: BrandPresentation(brand: brand))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal)
    }

    private var featuredSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Featured")
                .font(.title3.bold())
                .padding(.horizontal)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(brands.prefix(6)) { brand in
                        Button {
                            selectedBrand = brand
                        } label: {
                            FeaturedBrandCard(item: BrandPresentation(brand: brand, imageHeight: 140))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal)
                .scrollTargetLayout()
            }
            .scrollTargetBehavior(.viewAligned)
        }
    }
}

#Preview {
    BrandsView(token: "preview-token")
}
