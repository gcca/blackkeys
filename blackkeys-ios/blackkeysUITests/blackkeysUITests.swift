//
//  blackkeysUITests.swift
//  blackkeysUITests
//
//  Created by gcca on 20/09/26.
//

import XCTest

final class blackkeysUITests: XCTestCase {

    override func setUpWithError() throws {
        // Put setup code here. This method is called before the invocation of each test method in the class.

        // In UI tests it is usually best to stop immediately when a failure occurs.
        continueAfterFailure = false

        // In UI tests it’s important to set the initial state - such as interface orientation - required for your tests before they run. The setUp method is a good place to do this.
    }

    override func tearDownWithError() throws {
        // Put teardown code here. This method is called after the invocation of each test method in the class.
    }

    /// The username/password swap is animated, so "currently shown and
    /// interactive" is asserted via `.isHittable` and a predicate wait.
    private func waitForHittable(_ element: XCUIElement, isHittable: Bool, timeout: TimeInterval = 5) {
        let predicate = NSPredicate(format: "isHittable == %@", NSNumber(value: isHittable))
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: element)
        XCTAssertEqual(XCTWaiter().wait(for: [expectation], timeout: timeout), .completed)
    }

    @MainActor
    func testSignInFieldsArePresentOnLaunch() throws {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.buttons["eulaLink"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.images["eulaCheckbox"].exists)
        let usernameField = app.textFields["usernameTextField"]
        XCTAssertTrue(usernameField.waitForExistence(timeout: 5))
        waitForHittable(usernameField, isHittable: true)
        XCTAssertFalse(
            app.secureTextFields["passwordSecureField"].isHittable,
            "Password should stay hidden until the username is confirmed"
        )
    }

    @MainActor
    func testUsernameConfirmationRevealsPasswordAndCanBeReopened() throws {
        let app = XCUIApplication()
        app.launch()

        let usernameField = app.textFields["usernameTextField"]
        let passwordField = app.secureTextFields["passwordSecureField"]
        XCTAssertTrue(usernameField.waitForExistence(timeout: 5))
        usernameField.tap()
        usernameField.typeText("alex\n")

        waitForHittable(passwordField, isHittable: true)
        waitForHittable(usernameField, isHittable: false)
        XCTAssertTrue(app.buttons["usernameConfirmedLabel"].exists)

        app.buttons["usernameConfirmedLabel"].tap()

        waitForHittable(usernameField, isHittable: true)
        waitForHittable(passwordField, isHittable: false)
    }

    @MainActor
    func testTappingBackgroundDismissesKeyboardAndFieldStaysAboveIt() throws {
        let app = XCUIApplication()
        app.launch()

        let usernameField = app.textFields["usernameTextField"]
        XCTAssertTrue(usernameField.waitForExistence(timeout: 5))
        usernameField.tap()

        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        XCTAssertLessThanOrEqual(usernameField.frame.maxY, keyboard.frame.minY)
        XCTAssertFalse(app.buttons["closeKeyboardButton"].exists)

        app.coordinate(withNormalizedOffset: CGVector(dx: 0.1, dy: 0.2)).tap()

        let keyboardIsGone = NSPredicate(format: "exists == false")
        let expectation = XCTNSPredicateExpectation(predicate: keyboardIsGone, object: keyboard)
        XCTAssertEqual(XCTWaiter().wait(for: [expectation], timeout: 5), .completed)
    }

    @MainActor
    func testEulaCanBeAcceptedThenRejected() throws {
        let app = XCUIApplication()
        app.launch()

        let eulaLink = app.buttons["eulaLink"]
        XCTAssertTrue(eulaLink.waitForExistence(timeout: 5))
        XCTAssertTrue(app.images["eulaCheckbox"].exists)

        eulaLink.tap()
        XCTAssertTrue(app.buttons["eulaAcceptButton"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["eulaRejectButton"].exists)

        app.buttons["eulaAcceptButton"].tap()
        XCTAssertTrue(eulaLink.waitForExistence(timeout: 5))
        XCTAssertFalse(app.images["eulaCheckbox"].exists)

        eulaLink.tap()
        XCTAssertTrue(app.buttons["eulaRejectButton"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["eulaAcceptButton"].exists)

        app.buttons["eulaRejectButton"].tap()
        XCTAssertTrue(eulaLink.waitForExistence(timeout: 5))
        XCTAssertTrue(app.images["eulaCheckbox"].exists)
    }

    @MainActor
    func testLaunchPerformance() throws {
        // This measures how long it takes to launch your application.
        measure(metrics: [XCTApplicationLaunchMetric()]) {
            XCUIApplication().launch()
        }
    }
}
