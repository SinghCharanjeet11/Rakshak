# public/

Static files served from the site root. `public/logo.svg` is reachable at `/logo.svg`.

Drop brand assets here (logo, wordmark, og image). Anything Next.js special-cases as an
icon lives in `app/` instead, not here — see below.

| Put it here | Reached at |
|---|---|
| `public/logo.svg` | `/logo.svg` |
| `public/logo-dark.svg` | `/logo-dark.svg` |

Next.js App Router auto-wires these from `app/`, no `<link>` tag needed:

| File | Becomes |
|---|---|
| `app/icon.svg` (or `.png`) | the favicon |
| `app/apple-icon.png` (180x180) | the iOS home-screen icon |
| `app/opengraph-image.png` (1200x630) | the link preview card |
