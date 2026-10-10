import SwiftUI

/// Placeholders with the shape of the content that is on its way.
///
/// A screen that has nothing yet draws these instead of a spinner, so the
/// layout is there before the data is. They carry a slow sheen and are hidden
/// from assistive technology behind one "Loading" label.
struct SkeletonBlock: View {
    var width: CGFloat? = nil
    var height: CGFloat = 12
    var radius: CGFloat = 6
    @Environment(\.accent) private var accent

    var body: some View {
        RoundedRectangle(cornerRadius: radius, style: .continuous)
            .fill(accent.palette.line)
            .frame(width: width, height: height)
    }
}

/// Fades the placeholders in and out while they are on screen.
private struct Sheen: ViewModifier {
    @State private var dim = false

    func body(content: Content) -> some View {
        content
            .opacity(dim ? 0.45 : 1)
            .onAppear { withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { dim = true } }
    }
}

extension View {
    func skeletonSheen(label: String) -> some View {
        modifier(Sheen())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(label)
    }
}

/// The inbox while its first page loads: rows the size of real conversations.
struct InboxSkeleton: View {
    var rows = 8
    let label: String
    @Environment(\.accent) private var accent

    var body: some View {
        VStack(spacing: 0) {
            ForEach(0..<rows, id: \.self) { index in
                HStack(alignment: .top, spacing: 13) {
                    SkeletonBlock(width: 48, height: 48, radius: 18)
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            SkeletonBlock(width: index.isMultiple(of: 2) ? 140 : 110, height: 14)
                            Spacer()
                            SkeletonBlock(width: 40, height: 10)
                        }
                        SkeletonBlock(height: 12)
                        SkeletonBlock(width: index.isMultiple(of: 3) ? 180 : 120, height: 12)
                        SkeletonBlock(width: 90, height: 10).padding(.top, 2)
                    }
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 14)
                Rectangle().fill(accent.palette.line).frame(height: 0.5).padding(.leading, 83)
            }
            Spacer(minLength: 0)
        }
        .skeletonSheen(label: label)
    }
}

/// A thread while its messages load: bubbles on both sides.
struct ChatSkeleton: View {
    let label: String

    var body: some View {
        VStack(spacing: 10) {
            Spacer(minLength: 0)
            bubble(width: 220, lines: 2, outgoing: false)
            bubble(width: 170, lines: 1, outgoing: true)
            bubble(width: 240, lines: 3, outgoing: false)
            bubble(width: 200, lines: 2, outgoing: true)
            bubble(width: 150, lines: 1, outgoing: false)
        }
        .padding(.horizontal, 14)
        .padding(.bottom, 12)
        .skeletonSheen(label: label)
    }

    private func bubble(width: CGFloat, lines: Int, outgoing: Bool) -> some View {
        HStack {
            if outgoing { Spacer(minLength: 40) }
            VStack(alignment: .leading, spacing: 6) {
                ForEach(0..<lines, id: \.self) { line in
                    SkeletonBlock(width: line == lines - 1 ? width * 0.6 : width, height: 11)
                }
            }
            .padding(12)
            .background(SkeletonBlockBackground(), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            if !outgoing { Spacer(minLength: 40) }
        }
    }
}

private struct SkeletonBlockBackground: ShapeStyle {
    func resolve(in environment: EnvironmentValues) -> some ShapeStyle {
        environment.accent.palette.line.opacity(0.45)
    }
}

/// The directory while it loads: name, detail line, count.
struct ContactsSkeleton: View {
    var rows = 8
    let label: String
    @Environment(\.accent) private var accent

    var body: some View {
        VStack(spacing: 0) {
            ForEach(0..<rows, id: \.self) { index in
                HStack(spacing: 12) {
                    SkeletonBlock(width: 48, height: 48, radius: 18)
                    VStack(alignment: .leading, spacing: 8) {
                        SkeletonBlock(width: index.isMultiple(of: 2) ? 150 : 120, height: 14)
                        SkeletonBlock(width: 180, height: 11)
                        SkeletonBlock(width: 100, height: 11)
                    }
                    Spacer()
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                Rectangle().fill(accent.palette.line).frame(height: 0.5).padding(.leading, 20)
            }
            Spacer(minLength: 0)
        }
        .skeletonSheen(label: label)
    }
}
