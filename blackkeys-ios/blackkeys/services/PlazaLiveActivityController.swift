import ActivityKit

/// Owns the brand Live Activity, which exists so Plaza San Miguel's mark sits in
/// the Dynamic Island. It is started once at app launch rather than by any
/// screen — note that iOS only renders it while the app is *not* frontmost.
enum PlazaLiveActivityController {
    static func start() {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }

        // A Live Activity outlives the process that requested it, so an earlier
        // launch's activity is usually still running. Requesting unconditionally
        // would stack a new one on every launch.
        guard Activity<PlazaActivityAttributes>.activities.isEmpty else { return }

        _ = try? Activity.request(
            attributes: PlazaActivityAttributes(),
            content: .init(state: .init(), staleDate: nil)
        )
    }
}
