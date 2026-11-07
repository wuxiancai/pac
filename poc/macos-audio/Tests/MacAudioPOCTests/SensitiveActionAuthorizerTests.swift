import LocalAuthentication
import Testing
@testable import MacAudioPOC

@MainActor
@Test func sensitiveActionAuthenticationAcceptsBiometricsOrDevicePasscode() {
    #expect(
        TouchIDAuthorizer.authenticationPolicy.rawValue
            == LAPolicy.deviceOwnerAuthentication.rawValue
    )
}
