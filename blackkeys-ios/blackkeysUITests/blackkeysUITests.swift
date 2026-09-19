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

    @MainActor
    func testSignInFieldsArePresentOnLaunch() throws {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.buttons["eulaLink"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.images["eulaCheckbox"].exists)
        XCTAssertTrue(app.textFields["usernameTextField"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.secureTextFields["passwordSecureField"].exists)
        XCTAssertTrue(app.buttons["signInButton"].exists)
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
