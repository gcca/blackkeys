import ActivityKit
import SwiftUI
import WidgetKit

/// Artwork lives in `blackkeysWidget/Assets.xcassets`, not the app's catalog:
/// these views render in the widget extension's own process, which cannot read
/// the main app bundle. `PlazaBadge` is the square anniversary mark cropped out
/// of the full lockup — the compact leading slot is only ~24pt wide, where the
/// 4.66:1 wordmark would be an illegible smear.
struct PlazaLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: PlazaActivityAttributes.self) { _ in
            wordmark
                .frame(maxWidth: .infinity)
                .padding()
                .activityBackgroundTint(Color.black)
                .activitySystemActionForegroundColor(Color.white)
        } dynamicIsland: { _ in
            DynamicIsland {
                DynamicIslandExpandedRegion(.center) {
                    wordmark
                }
            } compactLeading: {
                badge
            } compactTrailing: {
                EmptyView()
            } minimal: {
                badge
            }
        }
    }

    private var badge: some View {
        Image("PlazaBadge")
            .resizable()
            .scaledToFit()
            .accessibilityLabel("Plaza San Miguel")
    }

    private var wordmark: some View {
        Image("PlazaLogo")
            .resizable()
            .scaledToFit()
            .accessibilityLabel("Plaza San Miguel")
    }
}
