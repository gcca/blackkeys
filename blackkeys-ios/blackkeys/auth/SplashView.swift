import SwiftUI

struct SplashView: View {
    let onFinished: () -> Void

    @State private var isAnimating = false

    private var backgroundVideoURL: URL {
        Bundle.main.url(forResource: "SplashBackground", withExtension: "mp4")!
    }

    var body: some View {
        ZStack {
            LoopingVideoView(url: backgroundVideoURL)
                .ignoresSafeArea()

            LinearGradient(
                colors: [
                    Color.black.opacity(0.55),
                    Color.black.opacity(0.15),
                    Color.black.opacity(0.65)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            VStack(spacing: 24) {
                Spacer()

                VStack(spacing: 4) {
                    Text("PLAZA SAN MIGUEL")
                        .font(.title2.weight(.bold))
                        .tracking(2)
                        .foregroundStyle(.white)

                    Text("Black Keys")
                        .font(.subheadline)
                        .foregroundStyle(.white.opacity(0.8))
                }
                .opacity(isAnimating ? 1 : 0)
                .offset(y: isAnimating ? 0 : 8)

                Spacer()

                ProgressView()
                    .tint(.white)
                    .padding(.bottom, 40)
            }
        }
        .accessibilityIdentifier("splashView")
        .onAppear {
            withAnimation(.spring(response: 0.6, dampingFraction: 0.7)) {
                isAnimating = true
            }
        }
        .task {
            try? await Task.sleep(for: .seconds(2))
            onFinished()
        }
    }
}

#Preview {
    SplashView {}
}
