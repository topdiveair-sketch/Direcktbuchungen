# Deployment checklist

The repository is ready for deployment once the following GitHub Environment secrets exist in `growth-engine-production`:

Required:
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `BOOKING_WORKER_URL`
- `ADMIN_TOKEN` (minimum 24 characters)
- `RUNTIME_BASE_URL` (the final workers.dev/custom-domain base URL)

Optional:
- `WINDIS_DATA_URL`

The deployment workflow performs, in order:
1. dependency install
2. preflight validation
3. Wrangler deployment with non-secret data-source variables
4. installation of `ADMIN_TOKEN` as a Cloudflare secret
5. public `/health` verification
6. first authenticated live planning run

No publishing, outbound partner messaging, or ad-spend executor exists in this release. Those actions remain impossible even after deployment.

Recommended first production validation:
- open `/health`
- open `/approval-ui`
- use the configured Agent base URL and ADMIN_TOKEN in the Approval UI
- confirm Booking availability signals are present
- confirm Windis signals use either the live URL or the reviewed seed fallback
- review all warnings
