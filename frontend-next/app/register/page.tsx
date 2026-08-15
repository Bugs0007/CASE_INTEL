import Link from "next/link";

export default function RegisterPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-page">
      <div className="w-[400px] max-w-[calc(100vw-40px)]">
        <div className="text-center mb-7">
          <div className="font-serif text-[26px] text-gray-900">Case Intel</div>
          <div className="text-sm text-gray-500 mt-1.5">Access is by invitation</div>
        </div>

        <div className="ci-card p-8 text-center">
          <p className="text-sm text-gray-600 leading-relaxed">
            Case Intel is open to a small set of practices right now. To request access, email{" "}
            <a href="mailto:samallabhagath@gmail.com" className="text-accent font-semibold hover:underline">
              samallabhagath@gmail.com
            </a>{" "}
            and you&apos;ll be sent an account once approved.
          </p>
        </div>
        <div className="text-center mt-[18px] text-[13px] text-gray-400">
          Already have an account?{" "}
          <Link href="/login" className="text-accent font-semibold hover:underline">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
