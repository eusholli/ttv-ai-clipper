import { SignIn } from "@clerk/clerk-react";

const SignInPage = () => {
  return (
    <div className="auth-container">
      <SignIn 
        routing="path" 
        path="/sign-in" 
        signUpUrl="/sign-up"
        forceRedirectUrl="/user-profile"
        appearance={{
          elements: {
            rootBox: "auth-root",
            card: "auth-card",
            headerTitle: "auth-title",
            headerSubtitle: "auth-subtitle",
            socialButtonsBlockButton: "auth-social-button",
            formButtonPrimary: "auth-submit-button",
            footerActionLink: "auth-link"
          }
        }}
      />
    </div>
  );
};

export default SignInPage;
