import ActivityKit

/// Carries no state: the activity exists only to keep Plaza San Miguel's mark
/// in the Dynamic Island, so there is nothing to update after `request`.
struct PlazaActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {}
}
