import AVFoundation
import SwiftUI

struct LoopingVideoView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> LoopingPlayerUIView {
        LoopingPlayerUIView(url: url)
    }

    func updateUIView(_ uiView: LoopingPlayerUIView, context: Context) {}
}

final class LoopingPlayerUIView: UIView {
    private let playerLayer = AVPlayerLayer()
    private let queuePlayer = AVQueuePlayer()
    private var looper: AVPlayerLooper?

    init(url: URL) {
        super.init(frame: .zero)

        let item = AVPlayerItem(url: url)
        looper = AVPlayerLooper(player: queuePlayer, templateItem: item)
        queuePlayer.isMuted = true
        queuePlayer.play()

        playerLayer.player = queuePlayer
        playerLayer.videoGravity = .resizeAspectFill
        layer.addSublayer(playerLayer)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        playerLayer.frame = bounds
    }
}
