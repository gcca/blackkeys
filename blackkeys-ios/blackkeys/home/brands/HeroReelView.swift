import AVFoundation
import SwiftUI

/// Which bundled videos fill the hero, and how the reel steps through them.
enum HeroReel {
    /// Bundled `Hero*.mp4` files in name order, so adding a file is enough.
    static func videoURLs(in urls: [URL]) -> [URL] {
        urls
            .filter { $0.pathExtension.lowercased() == "mp4" && $0.lastPathComponent.hasPrefix("Hero") }
            .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
    }

    static var bundledVideoURLs: [URL] {
        videoURLs(in: Bundle.main.urls(forResourcesWithExtension: "mp4", subdirectory: nil) ?? [])
    }

    /// The page after `index`, wrapping from the last back to the first.
    static func nextIndex(after index: Int, count: Int) -> Int {
        count > 0 ? (index + 1) % count : 0
    }
}

/// The hero banner: the mall's gradient when no video is bundled, otherwise
/// the bundled videos as a swipeable, auto-advancing reel (a single video just
/// loops, with no paging dots).
struct HeroReelView: View {
    /// False while something covers the feed (e.g. the brand detail).
    var isPlaying = true
    var urls: [URL] = HeroReel.bundledVideoURLs

    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var selection = 0
    @State private var isVisible = true

    private static let height: CGFloat = 160

    var body: some View {
        Group {
            if urls.isEmpty {
                gradient
            } else {
                reel
            }
        }
        .frame(height: Self.height)
        .clipShape(RoundedRectangle(cornerRadius: 20))
        .overlay {
            RoundedRectangle(cornerRadius: 20).strokeBorder(.separator, lineWidth: 1)
        }
        .onAppear { isVisible = true }
        .onDisappear { isVisible = false }
        .accessibilityIdentifier("brandsHeroReel")
    }

    private var reel: some View {
        let active = isPlaying && isVisible && scenePhase == .active && !reduceMotion
        return TabView(selection: $selection) {
            ForEach(Array(urls.enumerated()), id: \.offset) { index, url in
                ReelPlayerView(
                    url: url,
                    isActive: active && selection == index,
                    loops: urls.count == 1
                ) {
                    withAnimation { selection = HeroReel.nextIndex(after: index, count: urls.count) }
                }
                .tag(index)
                .accessibilityHidden(true)
            }
        }
        .tabViewStyle(.page(indexDisplayMode: urls.count > 1 ? .automatic : .never))
    }

    /// The mall's 4 brand colors (sampled from its official logo).
    private var gradient: some View {
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
    }
}

/// One muted video that plays only while `isActive` (and rewinds when it
/// stops), then either loops or reports the end.
private struct ReelPlayerView: UIViewRepresentable {
    let url: URL
    let isActive: Bool
    let loops: Bool
    let onEnded: () -> Void

    func makeUIView(context: Context) -> ReelPlayerUIView {
        ReelPlayerUIView(url: url)
    }

    func updateUIView(_ view: ReelPlayerUIView, context: Context) {
        view.loops = loops
        view.onEnded = onEnded
        view.setActive(isActive)
    }
}

private final class ReelPlayerUIView: UIView {
    var loops = false
    var onEnded: () -> Void = {}

    private let player: AVPlayer
    private let playerLayer = AVPlayerLayer()
    private var endObserver: NSObjectProtocol?

    init(url: URL) {
        let item = AVPlayerItem(url: url)
        player = AVPlayer(playerItem: item)
        super.init(frame: .zero)

        player.isMuted = true
        playerLayer.player = player
        playerLayer.videoGravity = .resizeAspectFill
        layer.addSublayer(playerLayer)

        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            if loops {
                player.seek(to: .zero)
                player.play()
            } else {
                onEnded()
            }
        }
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
    }

    func setActive(_ active: Bool) {
        if active {
            player.play()
        } else {
            player.pause()
            player.seek(to: .zero)
        }
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        playerLayer.frame = bounds
    }
}
