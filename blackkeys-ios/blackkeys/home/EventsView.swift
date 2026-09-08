import SwiftUI

private struct MallEvent: Identifiable {
    let id = UUID()
    let title: String
    let category: String
    let day: String
    let month: String
    let time: String
    let location: String
    let systemImage: String
    let tint: Color
}

struct EventsView: View {
    private let topContentInset: CGFloat
    private let onScrollDepthChange: (CGFloat) -> Void

    private let featuredEvents: [MallEvent] = [
        MallEvent(title: "Live Jazz Night", category: "Music", day: "12", month: "OCT", time: "7:00 PM", location: "Central Atrium", systemImage: "music.note", tint: .purple),
        MallEvent(title: "Fashion Week Runway", category: "Fashion", day: "18", month: "OCT", time: "6:00 PM", location: "Main Stage", systemImage: "sparkles", tint: .pink),
        MallEvent(title: "Weekend Food Fair", category: "Food", day: "25", month: "OCT", time: "11:00 AM", location: "Food Court", systemImage: "fork.knife", tint: .orange),
    ]

    private let upcomingEvents: [MallEvent] = [
        MallEvent(title: "Kids Painting Workshop", category: "Family", day: "14", month: "OCT", time: "3:00 PM", location: "Level 3 Activity Hall", systemImage: "paintpalette.fill", tint: .green),
        MallEvent(title: "Tech Expo", category: "Technology", day: "16", month: "OCT", time: "10:00 AM", location: "Level 2 Wing A", systemImage: "cpu.fill", tint: .indigo),
        MallEvent(title: "Holiday Light Show", category: "Entertainment", day: "20", month: "OCT", time: "8:00 PM", location: "Central Atrium", systemImage: "sparkle", tint: .yellow),
        MallEvent(title: "Yoga at the Plaza", category: "Wellness", day: "22", month: "OCT", time: "8:00 AM", location: "Rooftop Garden", systemImage: "figure.mind.and.body", tint: .teal),
        MallEvent(title: "Charity Book Drive", category: "Community", day: "27", month: "OCT", time: "9:00 AM", location: "Level 1 Wing D", systemImage: "book.closed.fill", tint: .brown),
    ]

    init(
        topContentInset: CGFloat = 12,
        onScrollDepthChange: @escaping (CGFloat) -> Void = { _ in }
    ) {
        self.topContentInset = topContentInset
        self.onScrollDepthChange = onScrollDepthChange
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                eventSection(title: "Featured") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 16) {
                            ForEach(featuredEvents) { event in
                                FeaturedEventCard(event: event)
                            }
                        }
                        .padding(.horizontal)
                        .scrollTargetLayout()
                    }
                    .scrollTargetBehavior(.viewAligned)
                }

                eventSection(title: "Upcoming") {
                    LazyVStack(spacing: 12) {
                        ForEach(upcomingEvents) { event in
                            EventRow(event: event)
                                .padding(.horizontal)
                        }
                    }
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
    }

    @ViewBuilder
    private func eventSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.title3.bold())
                .padding(.horizontal)

            content()
        }
    }
}

private struct FeaturedEventCard: View {
    let event: MallEvent

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            LinearGradient(
                colors: [event.tint, event.tint.opacity(0.6)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            Image(systemName: event.systemImage)
                .font(.system(size: 40))
                .foregroundStyle(.white.opacity(0.35))
                .frame(maxWidth: .infinity, alignment: .trailing)
                .padding(.trailing, 12)

            VStack(alignment: .leading, spacing: 6) {
                dateBadge

                Text(event.category.uppercased())
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.white.opacity(0.85))
                Text(event.title)
                    .font(.headline)
                    .foregroundStyle(.white)
            }
            .padding(12)
        }
        .frame(width: 200, height: 150)
        .clipShape(RoundedRectangle(cornerRadius: 20))
    }

    private var dateBadge: some View {
        VStack(spacing: 0) {
            Text(event.day)
                .font(.headline.bold())
            Text(event.month)
                .font(.caption2.weight(.semibold))
        }
        .foregroundStyle(event.tint)
        .frame(width: 40, height: 40)
        .background(.white, in: RoundedRectangle(cornerRadius: 10))
    }
}

private struct EventRow: View {
    let event: MallEvent

    var body: some View {
        HStack(spacing: 14) {
            VStack(spacing: 0) {
                Text(event.day)
                    .font(.headline.bold())
                Text(event.month)
                    .font(.caption2.weight(.semibold))
            }
            .foregroundStyle(.white)
            .frame(width: 48, height: 48)
            .background(event.tint, in: RoundedRectangle(cornerRadius: 12))

            VStack(alignment: .leading, spacing: 2) {
                Text(event.title)
                    .font(.body.weight(.semibold))
                Text("\(event.time) · \(event.location)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
        .padding(12)
        .background(.fill.tertiary, in: RoundedRectangle(cornerRadius: 16))
    }
}

#Preview {
    EventsView()
}
