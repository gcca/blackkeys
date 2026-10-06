import SwiftUI

enum HomeTab: Hashable {
    case stores
    case events
    case search

    var title: String {
        switch self {
        case .stores: "Stores"
        case .events: "Events"
        case .search: "Search"
        }
    }

    var systemImage: String {
        switch self {
        case .stores: "bag"
        case .events: "sparkles"
        case .search: "magnifyingglass"
        }
    }

    var accessibilityIdentifier: String {
        switch self {
        case .stores: "homeTabStoresButton"
        case .events: "homeTabEventsButton"
        case .search: "homeTabSearchButton"
        }
    }
}

struct HomeView: View {
    private static let feedTopSpacing: CGFloat = 12

    let session: AuthSession

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var selectedTab: HomeTab = .stores
    @State private var storesScrollDepth: CGFloat = 0
    @State private var eventsScrollDepth: CGFloat = 0
    @State private var topBarHeight: CGFloat = 44
    @State private var mapDestination: MapDestination?
    @State private var isShowingDebugMenu = false

    var body: some View {
        TabView(selection: $selectedTab) {
            Tab(value: HomeTab.stores) {
                BrandsView(
                    token: session.token,
                    topContentInset: topBarHeight + Self.feedTopSpacing,
                    onShowDirections: { destination in
                        mapDestination = destination
                        selectedTab = .search
                    },
                    onScrollDepthChange: { scrollDepth in
                        storesScrollDepth = scrollDepth
                    }
                )
            } label: {
                tabLabel(for: .stores)
            }

            Tab(value: HomeTab.events) {
                EventsView(topContentInset: topBarHeight + Self.feedTopSpacing) { scrollDepth in
                    eventsScrollDepth = scrollDepth
                }
            } label: {
                tabLabel(for: .events)
            }

            Tab(value: HomeTab.search, role: .search) {
                SearchView(destination: mapDestination)
                    .safeAreaInset(edge: .top, spacing: 0) {
                        Color.clear
                            .frame(height: topBarHeight)
                            .accessibilityHidden(true)
                    }
            } label: {
                tabLabel(for: .search)
            }
        }
        .tabBarMinimizeBehavior(.never)
        .safeAreaInset(edge: .top, spacing: -topBarHeight) {
            ZStack(alignment: .top) {
                topBar
                    .padding(.horizontal)
                    .padding(.vertical, 8)
                    .onGeometryChange(for: CGFloat.self) { geometry in
                        geometry.size.height
                    } action: { oldValue, newValue in
                        guard oldValue != newValue else { return }
                        topBarHeight = newValue
                    }
                    .offset(y: -topBarOffset)
                    .opacity(topBarOpacity)
                    .allowsHitTesting(!isTopBarHidden)
                    .accessibilityHidden(isTopBarHidden)
            }
            .frame(height: topBarHeight, alignment: .top)
            .clipped()
            .environment(\.colorScheme, selectedTab == .search ? .light : colorScheme)
        }
        .scrollEdgeEffectStyle(.automatic, for: .top)
        .sheet(isPresented: $isShowingDebugMenu) {
            DebugMenuView()
        }
    }

    private var topBar: some View {
        HStack(alignment: .center, spacing: 8) {
            Image("PlazaLogo")
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(height: 28)
                .layoutPriority(1)
                .accessibilityLabel("Plaza San Miguel")

            Spacer(minLength: 0)

            VStack(alignment: .trailing, spacing: 0) {
                Text("Hi,")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(session.username)
                    .font(.subheadline.weight(.bold))
                    .lineLimit(1)
                    .truncationMode(.tail)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Hi, \(session.username)")
            .debugMenuTrigger(enabled: AppConfiguration.isDebugUser(session.username)) {
                isShowingDebugMenu = true
            }
        }
    }

    private var activeScrollDepth: CGFloat {
        switch selectedTab {
        case .stores:
            storesScrollDepth
        case .events:
            eventsScrollDepth
        case .search:
            0
        }
    }

    private var topBarOffset: CGFloat {
        guard selectedTab != .search else { return 0 }

        if reduceMotion {
            return activeScrollDepth > Self.feedTopSpacing ? topBarHeight : 0
        }

        return min(max(activeScrollDepth, 0), topBarHeight)
    }

    private var topBarOpacity: Double {
        reduceMotion && isTopBarHidden ? 0 : 1
    }

    private var isTopBarHidden: Bool {
        selectedTab != .search && topBarOffset >= topBarHeight
    }

    private func tabLabel(for tab: HomeTab) -> some View {
        Label(tab.title, systemImage: tab.systemImage)
            .accessibilityIdentifier(tab.accessibilityIdentifier)
    }
}

private extension View {
    /// Long-press (and a VoiceOver action) that opens the debug menu. Applied
    /// only for allowed users, so everyone else gets neither.
    @ViewBuilder
    func debugMenuTrigger(enabled: Bool, action: @escaping () -> Void) -> some View {
        if enabled {
            onLongPressGesture(minimumDuration: 0.8, perform: action)
                .accessibilityAction(named: "Debug menu", action)
        } else {
            self
        }
    }
}

#Preview {
    HomeView(session: AuthSession(username: "alex", token: "preview-token"))
}
