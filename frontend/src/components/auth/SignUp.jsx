import { SignUp } from "@clerk/clerk-react";

const SignUpPage = () => {
  return (
    <div className="auth-container">
      <SignUp 
        routing="path"
        path="/sign-up"
        signInUrl="/sign-in"
        fallbackRedirectUrl="/"
        appearance={{
          elements: {
            formButtonPrimary: {
              backgroundColor: '#007bff',
              '&:hover': { backgroundColor: '#0056b3' }
            }
          }
        }}
      />
    </div>
  );
};

export default SignUpPage;
