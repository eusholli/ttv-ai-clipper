import { SignUp } from "@clerk/clerk-react";

const SignUpPage = () => {
  return (
    <div className="auth-container">
      <SignUp 
        routing="path"
        path="/sign-up"
        signInUrl="/sign-in"
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

export default SignUpPage;
