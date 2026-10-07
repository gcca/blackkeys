import Foundation
import Testing
@testable import blackkeys

struct HeroReelTests {
    private func urls(_ names: [String]) -> [URL] {
        names.map { URL(fileURLWithPath: "/bundle/\($0)") }
    }

    @Test func keepsOnlyHeroMP4sInNaturalNameOrder() {
        let result = HeroReel.videoURLs(in: urls(["Hero10.mp4", "SplashBackground.mp4", "Hero2.mp4", "Hero1.MP4", "Hero3.mov"]))
        #expect(result.map(\.lastPathComponent) == ["Hero1.MP4", "Hero2.mp4", "Hero10.mp4"])
    }

    @Test func noHeroVideosGivesAnEmptyList() {
        #expect(HeroReel.videoURLs(in: urls(["SignInBackground.mp4"])).isEmpty)
    }

    @Test func nextIndexWrapsFromTheLastToTheFirst() {
        #expect(HeroReel.nextIndex(after: 0, count: 3) == 1)
        #expect(HeroReel.nextIndex(after: 2, count: 3) == 0)
        #expect(HeroReel.nextIndex(after: 0, count: 1) == 0)
        #expect(HeroReel.nextIndex(after: 0, count: 0) == 0)
    }
}
