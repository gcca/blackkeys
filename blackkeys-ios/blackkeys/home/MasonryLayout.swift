import SwiftUI

/// A column-balanced masonry layout: subviews are proposed an exact, fixed
/// column width (never negotiated — this is what prevents long text content
/// from ever overflowing the container), measured for their *real* height
/// via `sizeThatFits`, then greedily placed into whichever column currently
/// has the smallest accumulated height. Preserves input order for
/// accessibility traversal; only the resulting geometry is staggered.
struct MasonryLayout: Layout {
    var columns: Int = 2
    var horizontalSpacing: CGFloat = 12
    var verticalSpacing: CGFloat = 12

    private func columnWidth(for totalWidth: CGFloat) -> CGFloat {
        let totalSpacing = horizontalSpacing * CGFloat(columns - 1)
        return max(0, (totalWidth - totalSpacing) / CGFloat(columns))
    }

    /// Shared geometry computation used by both `sizeThatFits` and
    /// `placeSubviews` so the two calls can never disagree about placement
    /// (no `Cache` type needed for a feed this size — recomputing from
    /// scratch in both is a feature here, not a missed optimization).
    private func columnAssignments(
        subviews: Subviews,
        columnWidth: CGFloat
    ) -> (positions: [CGPoint], columnHeights: [CGFloat]) {
        var columnHeights = [CGFloat](repeating: 0, count: columns)
        var positions: [CGPoint] = []
        positions.reserveCapacity(subviews.count)

        for subview in subviews {
            let height = subview.sizeThatFits(
                ProposedViewSize(width: columnWidth, height: nil)
            ).height

            let shortestColumn = columnHeights
                .enumerated()
                .min(by: { $0.element < $1.element })!
                .offset

            let x = CGFloat(shortestColumn) * (columnWidth + horizontalSpacing)
            let y = columnHeights[shortestColumn]
            positions.append(CGPoint(x: x, y: y))

            columnHeights[shortestColumn] += height + verticalSpacing
        }

        return (positions, columnHeights)
    }

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout Void
    ) -> CGSize {
        let totalWidth = proposal.width ?? 0
        guard totalWidth > 0, !subviews.isEmpty else {
            return CGSize(width: totalWidth, height: 0)
        }

        let width = columnWidth(for: totalWidth)
        let (_, columnHeights) = columnAssignments(subviews: subviews, columnWidth: width)
        let maxHeight = max(0, (columnHeights.max() ?? 0) - verticalSpacing)
        return CGSize(width: totalWidth, height: maxHeight)
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout Void
    ) {
        guard !subviews.isEmpty else { return }

        let width = columnWidth(for: bounds.width)
        let (positions, _) = columnAssignments(subviews: subviews, columnWidth: width)

        for (index, subview) in subviews.enumerated() {
            let point = positions[index]
            subview.place(
                at: CGPoint(x: bounds.minX + point.x, y: bounds.minY + point.y),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: width, height: nil)
            )
        }
    }
}
