# What Drive scope and verification does live sync need?

- **Date:** 2026-09-16
- **Ticket:** What Drive scope and verification does live sync need?
- **Extends:** [DennieDan/knowledge-graph#2](https://github.com/DennieDan/knowledge-graph/issues/2) (individual Google Account vs Google Workspace user flows)

## Short recommendation

Commit the MVP connector to **Google Sign-In identity scopes plus one Drive scope:**

| Purpose | Scope | Classification |
| --- | --- | --- |
| Sign-in / identity | `openid`, `email`, `profile` (or the equivalent `userinfo.email` / `userinfo.profile`) | Non-sensitive (pre-filled on the consent screen) |
| Read Drive files **and** sharing ACLs; live change feed | `https://www.googleapis.com/auth/drive.readonly` | **Restricted** |

Do **not** request `https://www.googleapis.com/auth/drive` (full). That scope can create, edit, share, and delete files. Google’s own consent copy for it includes “Upload and download your files”, “Delete your files”, and “Share and stop sharing your files with others” ([Requesting Minimum Scopes](https://support.google.com/cloud/answer/13807380)).

Do **not** treat `drive.file` as the live-sync scope. It is non-sensitive, but it only covers files the user opens with the app, creates with the app, or shares with the app via Picker / Open with ([Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)). It also grants edit/create/delete on those files ([OAuth 2.0 Scopes for Google APIs](https://developers.google.com/identity/protocols/oauth2/scopes)).

Do **not** use `drive.metadata.readonly` as the only Drive scope. Google states that both metadata scopes “strictly prohibit access to file content” ([Manage file metadata](https://developers.google.com/workspace/drive/api/guides/file-metadata)). `files.export` does not list `drive.metadata.readonly` as an authorized scope ([files.export](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/export)).

**Build now, verify later.** Google’s unverified-apps help page says you can continue to build and test while waiting to complete verification, and that development/test builds do not need verification until you launch publicly ([Unverified apps](https://support.google.com/cloud/answer/7454865)). Put the Cloud project in **Testing**, add up to **100 test users**, and expect a tester warning plus **7-day refresh-token expiry** ([Manage App Audience](https://support.google.com/cloud/answer/15549945)). Do not publish an unverified restricted-scope app: published + unverified + restricted scopes still shows the danger UI and a lifetime **100-user cap** ([OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)).

**Verification path for production (External user type, multi-tenant, public GitHub):** brand verification → restricted-scope verification → CASA, because the app stores Drive data on its own servers. Google’s OAuth FAQ lists expected completion of **2–3 business days** (brand), **10 business days** (sensitive), and **6 weeks** (restricted, including the security assessment), and says those estimates are not guaranteed ([OAuth verification FAQ](https://support.google.com/cloud/answer/13463817)). Google does not publish a CASA price; listed assessors that publish prices currently quote roughly **USD 675 (AL1, TAC Security) to USD 6,000 (Leviathan speed packages)** ([Google FAQ: Google does not charge](https://support.google.com/cloud/answer/13463817); [TAC Security CASA](https://tacsecurity.com/google-casa-cloud-application-security-assessment/); [Leviathan CASA](https://www.leviathansecurity.com/programs/google-casa-cloud-application-security-assessment)). Recertify every **12 months** from the Letter of Validation date ([Annual Recertification](https://support.google.com/cloud/answer/13463816)).

**Issue #2 implication:** individual Gmail users can only use per-user OAuth. Workspace customers can use the same per-user OAuth flow, and optionally an admin can mark the app Trusted or grant domain-wide delegation. Neither DWD nor “admin-trusted” changes the **scope string**. Internal-only / “own domain” exceptions do **not** apply to a public SaaS used by many companies ([When is verification not needed](https://support.google.com/cloud/answer/13464323); [Restricted scope verification — exceptions](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)).

---

## 1. Which OAuth scope reads files **and** sharing permissions?

### Official descriptions (quoted)

Google publishes two overlapping description sets. Both are first-party.

From [Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) (Drive API auth guide, last updated 2026-09-03 UTC):

| Scope | Drive API guide description | Drive API guide category |
| --- | --- | --- |
| `https://www.googleapis.com/auth/drive.file` | “Create new Drive files, or modify existing files, that you open with an app or that the user shares with an app while using the Google Picker API or the app's file picker.” | Non-sensitive |
| `https://www.googleapis.com/auth/drive` | “View and manage all your Drive files.” | Restricted |
| `https://www.googleapis.com/auth/drive.readonly` | “View and download all your Drive files.” | Restricted |
| `https://www.googleapis.com/auth/drive.metadata.readonly` | “View metadata for files in your Drive.” | Restricted |
| `https://www.googleapis.com/auth/drive.activity.readonly` | “View the activity record of files in your Drive.” | Restricted |

From [OAuth 2.0 Scopes for Google APIs](https://developers.google.com/identity/protocols/oauth2/scopes) (the cross-API scope catalog):

| Scope | Catalog description |
| --- | --- |
| `https://www.googleapis.com/auth/drive` | “See, edit, create, and delete all of your Google Drive files” |
| `https://www.googleapis.com/auth/drive.file` | “See, edit, create, and delete only the specific Google Drive files you use with this app” |
| `https://www.googleapis.com/auth/drive.readonly` | “See and download all your Google Drive files” |
| `https://www.googleapis.com/auth/drive.metadata.readonly` | “See information about your Google Drive files” |
| `https://www.googleapis.com/auth/drive.activity.readonly` | “View the activity record of files in your Google Drive” |

Google Cloud’s reviewer help page adds the user-visible consent copy for `drive.readonly`: “See your Google Drive files / Download your files / See the names and emails of people you share files with” ([Requesting Minimum Scopes](https://support.google.com/cloud/answer/13807380)). The same page’s consent copy for `drive.metadata.readonly` includes “The names and email addresses of people you share files with” but **not** download. The consent copy for full `drive` includes delete, share, and organize.

### What each scope actually enables (method-level)

Google documents authorized scopes on each REST method. The tables below are those method pages, not inference.

**File content**

| Method | What it does | `drive.readonly` | `drive.metadata.readonly` | `drive.file` | `drive` |
| --- | --- | --- | --- | --- | --- |
| [`files.get`](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get) | Metadata or content (`alt=media`) | yes | listed, but content is blocked (see below) | yes, for app-opened files | yes |
| [`files.export`](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/export) | Export Docs/Sheets/Slides bytes | yes | **not listed** | yes | yes |
| [`files.list`](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list) | List / search files | yes | yes (metadata only) | yes | yes |

Google’s metadata guide is explicit: `drive.metadata` and `drive.metadata.readonly` “strictly prohibit access to file content”, and “the Drive API will block attempts to modify or download the file if your app only has the `drive.metadata.readonly` scope” ([Manage file metadata](https://developers.google.com/workspace/drive/api/guides/file-metadata)).

**Sharing permissions**

| Method | What it does | `drive.readonly` | `drive.metadata.readonly` | `drive.file` | `drive` |
| --- | --- | --- | --- | --- | --- |
| [`permissions.list`](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/list) | List a file’s or shared drive’s ACL | yes | yes | yes | yes |
| [`permissions.get`](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions) | Get one permission | same family of Drive scopes as list (see permissions resource methods) | same | same | same |
| `files.get` / `files.list` field `permissions[]` | Embedded ACL on the File resource | possible, with caveats in §6 | possible, with caveats | possible, with caveats | possible, with caveats |

So: **metadata.readonly can see sharing ACLs but cannot read file bytes. drive.readonly can do both.** `drive.file` can do both **only for files in the app’s per-file grant set**.

**Live sync (Changes API + push notifications)**

Google Drive push notifications do **not** introduce a separate webhook OAuth scope. You watch `files` or `changes` with the same Drive scopes as the resource ([Notifications for resource changes](https://developers.google.com/workspace/drive/api/guides/push); [`changes.watch`](https://developers.google.com/workspace/drive/api/reference/rest/v3/changes/watch); [`files.watch`](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/watch)).

| Method | What it does | Authorized Drive scopes include |
| --- | --- | --- |
| [`changes.watch`](https://developers.google.com/workspace/drive/api/reference/rest/v3/changes/watch) | Subscribe to a user’s (or shared drive’s) change feed | `drive`, `drive.file`, `drive.readonly`, `drive.metadata`, `drive.metadata.readonly`, plus `drive.appdata` / `drive.meet.readonly` / `drive.photos.readonly` |
| [`changes.list`](https://developers.google.com/workspace/drive/api/reference/rest/v3/changes/list) | Page the changelog after a notification | same set |
| [`files.watch`](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/watch) | Subscribe to one file | same set |

Push-channel limits from the same notifications guide: maximum expiration **86400 seconds (1 day)** for `files` watch and **604800 seconds (1 week)** for `changes`; default expiration is 3600 seconds if unset; the webhook URL must be HTTPS with a valid (not self-signed) certificate; notifications have an empty body, so the app must call `files.get` or `changes.list` to learn what changed ([Notifications for resource changes](https://developers.google.com/workspace/drive/api/guides/push)). `X-Goog-Changed` can include `permissions` when a file’s ACL changes.

**Drive Activity API (optional, not required for live sync)**

[`activity.query`](https://developers.google.com/workspace/drive/activity/v2/reference/rest/v2/activity/query) is a different API. It is authorized **only** by:

- `https://www.googleapis.com/auth/drive.activity`
- `https://www.googleapis.com/auth/drive.activity.readonly`

Both are **Restricted** on the Drive scopes page ([Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)) and on Google Cloud’s restricted-scope list ([Restricted Scopes](https://support.google.com/cloud/answer/13464325)). This API queries *past activity* (who did what). It is not the change-notification channel. Live sync can be built with `changes.watch` + `changes.list` under `drive.readonly` alone.

### Which scope matches “read files + mirror sharing”?

**`drive.readonly` is the only listed scope that (a) downloads/exports file content for all of a user’s Drive, (b) authorizes `permissions.list`, and (c) does not grant write.** Google’s reviewer guidance says to downscope from full `drive` to `drive.readonly` “if your app needs to view the user’s files and/or folders within the app UI, but per-file selection with the `drive.file` scope via a file picker justifiably does not fit your use case” ([Requesting Minimum Scopes](https://support.google.com/cloud/answer/13807380)).

`drive.file` is Google’s preferred *non-sensitive* alternative when the product is “user picks files.” A live mirror of Drive plus sharing ACLs is the case Google describes as *not* fitting Picker.

### Restricted-scope use-case gate

Using any restricted Drive scope is allowed only for listed application types. Google states the same three categories in three first-party places:

1. “Backup and sync: Platform-specific and web apps that provide local sync or automatic backup of users' Drive files.”
2. “Productivity and education: Apps with a primary user interface that might involve interaction with Drive files, metadata, or permissions.”
3. “Reporting and security: Apps that provide user or customer insight into how files are shared or accessed.”

Sources: [Choose Google Drive API scopes — Qualifications for restricted scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth); [Google Drive API Terms of Service — Use of restricted scopes](https://developers.google.com/workspace/drive/api/terms); [Google Workspace user data and developer policy — Appropriate access to and use of Google Drive Scopes](https://developers.google.com/workspace/workspace-api-user-data-developer-policy).

A read-only live sync that mirrors file content and sharing into the product UI is closest to (1) and/or (2), and the sharing-mirror itself is the kind of ACL insight described in (3). Google, not this note, decides whether a submitted app qualifies.

---

## 2. Is that scope Restricted or Sensitive?

**`https://www.googleapis.com/auth/drive.readonly` is Restricted**, not Sensitive.

Google classifies it as Restricted in:

- The Drive API scopes table ([Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth))
- The Cloud Console restricted-scope list under “Drive API” ([Restricted Scopes](https://support.google.com/cloud/answer/13464325))
- Workspace Admin Console “Drive & Docs high-risk OAuth scopes” ([Control which apps access Google Workspace data](https://support.google.com/a/answer/7281227))

The **only Sensitive Drive API scope** on the Drive auth guide is `https://www.googleapis.com/auth/drive.apps.readonly` (“View apps authorized to access your Drive”) ([Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)). That scope is not needed to read files or ACLs.

Google’s definition of Restricted (Drive auth guide): “These scopes provide wide access to Google user data and require restricted scope OAuth App Verification.” ([Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth))

Google Workspace’s product policy defines Drive restricted scopes as: “Any Drive API scope that permits an application to: Read, modify, or manage the content or metadata of a user's Drive files, without the user individually granting file-by-file access.” ([Google Workspace user data and developer policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)). That sentence is why `drive.readonly` and `drive.metadata.readonly` are Restricted, while `drive.file` (file-by-file) is Non-sensitive.

Classification of the comparison set:

| Scope | Official classification | Primary source |
| --- | --- | --- |
| `drive.file` | Non-sensitive | [Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth); reviewer copy also says “Non-sensitive” ([Requesting Minimum Scopes](https://support.google.com/cloud/answer/13807380)) |
| `drive.apps.readonly` | Sensitive | [Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) |
| `drive` | Restricted | [Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth); [Restricted Scopes](https://support.google.com/cloud/answer/13464325) |
| `drive.readonly` | Restricted | same |
| `drive.metadata.readonly` | Restricted | same |
| `drive.activity` / `drive.activity.readonly` | Restricted | same |

If the app stores or transmits restricted-scope data on its own servers, Google requires a security assessment ([Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth); [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [Google API Services User Data Policy — Secure Data Handling](https://developers.google.com/terms/api-services-user-data-policy)). A Postgres mirror of Drive files and ACLs is server-side storage of restricted-scope data.

---

## 3. CASA / security assessment: cost, time, recertification, AL1 vs AL2, public repo

### When CASA is required

Google: “Every app that requests access to Google users' restricted data and has the ability to access data from or through a third-party server must go through a security assessment from Google-empanelled security assessors.” The assessment “help[s] keep Google users' data safe by verifying that all apps that access Google user data demonstrate the capability to handle data securely and to delete user data upon a user's request.” Google standardizes this on the App Defense Alliance CASA framework ([Restricted scope verification — Security assessment](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [Security Assessment](https://support.google.com/cloud/answer/13465431)).

Google also says CASA is the **final** step of restricted-scope review, and “the Google Trust and Safety team will contact you when it is time to initiate the security assessment process” ([Security Assessment](https://support.google.com/cloud/answer/13465431)). ADA says a Framework-User-initiated assessment starts with a notification that includes the required tier/level and due date; developers then “Reach out to any preferred Authorized Assessor(s) to price and schedule” ([CASA Framework User Initiated Assessment](https://appdefensealliance.dev/casa/casa-start)).

### Google does not publish a price

Google’s OAuth FAQ: “Google does not charge the developer any fees for security assessment. … The cost for such a service is agreed on between the developer and the assessor without any involvement from Google. We encourage our developers to reachout to multiple assessors to find what works best for them.” ([OAuth verification FAQ](https://support.google.com/cloud/answer/13463817))

ADA likewise tells developers to get quotes from more than one authorized assessor ([CASA Framework User Initiated Assessment](https://appdefensealliance.dev/casa/casa-start)). **ADA’s own pages do not list dollar amounts.**

### Published prices from listed assessors (range, not a Google fee)

ADA’s CASA overview lists authorized lab partners including GDS Ltd–An Aon Group, Bishop Fox, KPMG, Leviathan Security, NCC Group, NST Cyber, Orange Cyberdefense South Africa, Prescient Security LLC, TAC Security, and DEKRA ([CASA overview](https://appdefensealliance.dev/casa/casa-beta)).

Assessors on that list that **publish numbers on their own sites** (retrieved 2026-09-16):

| Assessor | What they publish | Source |
| --- | --- | --- |
| **TAC Security** (ADA authorized lab) | AL1 Basic **USD 675**; AL1 Premium **USD 855**; AL1 Enterprise unlimited **USD 4500**; AL2 Enterprise **USD 5400**. FAQ still quotes older “Tier 2 / Tier 3” packaging at **USD 675 / 855 / 1800 / 4500**. | [TAC Google CASA page](https://tacsecurity.com/google-casa-cloud-application-security-assessment/); [TAC CASA FAQs](https://tacsecurity.com/esof-appsec-ada-casa-faqs/) |
| **Leviathan Security** (ADA authorized lab) | Three start-time packages: **USD 3,000** (start within 30 days), **USD 4,500** (10 days), **USD 6,000** (2 days), each with 1 round of retesting. The page describes AL1 vs AL2 but does **not** map those dollar figures to AL1 vs AL2. | [Leviathan CASA](https://www.leviathansecurity.com/programs/google-casa-cloud-application-security-assessment) |

**Not found in a primary source:** a single official ADA or Google price list; Bishop Fox / KPMG / NCC / GDS / DEKRA public CASA rate cards (those labs are listed; their public pages reviewed for this note did not state a CASA dollar amount). Treat any blog “typical range” as non-authoritative.

So the **documented published range from listed assessors is about USD 675–6,000 per assessment cycle**, depending on AL, package, and vendor. Quotes can sit outside that range; Google and ADA say to ask more than one lab.

### Timeline

| Step | What a primary source says | Source |
| --- | --- | --- |
| Brand verification | “typically takes 2-3 business days” if branding changed; FAQ table: **2–3 business days** | [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [OAuth verification FAQ](https://support.google.com/cloud/answer/13463817) |
| Sensitive scope verification | FAQ table: **10 business days** | [OAuth verification FAQ](https://support.google.com/cloud/answer/13463817) |
| Restricted scope verification (includes security assessment) | FAQ table: **6 weeks**. Estimates “are not guaranteed and will vary based on developer responsiveness.” Restricted-scope page: the process “can potentially take several weeks.” Unverified-apps help: depending on sensitivity, “verification might require several months.” | [OAuth verification FAQ](https://support.google.com/cloud/answer/13463817); [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [Unverified apps](https://support.google.com/cloud/answer/7454865) |
| When CASA starts | After other verification requirements; Google T&S emails you | [Security Assessment](https://support.google.com/cloud/answer/13465431) |
| CASA portal (legacy Tier 2 write-up) | Must be submitted for verification review **within 30 days of initiation** | [Complete your CASA](https://appdefensealliance.dev/casa/tier-2/complete-submit) |
| TAC Security (assessor, not Google) | “Assessment to LoV” **1–2 weeks** (AL1 Enterprise), **2–3 weeks** (AL1 Basic/Premium), **2–4 weeks** (AL2). After LOV, TAC says Google emails within **5–6 business days**. DAST/SAST scan “usually varies from 1–2 business days.” | [TAC Google CASA page](https://tacsecurity.com/google-casa-cloud-application-security-assessment/); [TAC CASA FAQs](https://tacsecurity.com/esof-appsec-ada-casa-faqs/) |
| Leviathan (assessor, not Google) | Time-to-**start**: 2 / 10 / 30 days. **Does not publish** total calendar time to LOV. | [Leviathan CASA](https://www.leviathansecurity.com/programs/google-casa-cloud-application-security-assessment) |

**ADA does not publish a standard number of weeks for an assessment.** Google’s 6-week restricted-verification figure is the only Google-owned end-to-end estimate, and Google marks it as unguaranteed.

### Annual recertification

- Apps that access restricted scopes must complete a security assessment **every 12 months**, counted from the previous Letter of Validation (LOV) effective date ([Annual Recertification](https://support.google.com/cloud/answer/13463816); [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) uses “Letter of Assessment (LOA)” for the same annual clock).
- “We require the annual CASA security reassessment to be a comprehensive test of your app, regardless of any changes made to the app.” ([Annual Recertification](https://support.google.com/cloud/answer/13463816); same wording in the [OAuth verification FAQ](https://support.google.com/cloud/answer/13463817))
- ADA: “All applications must be revalidated every year.” ([Assurance Levels](https://appdefensealliance.dev/casa/casa-tiering))
- Adding a new restricted scope may require reassessment covering that scope ([Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)).
- Google assigns AL1 or AL2; “Once an application has been validated at the highest level (AL2), it will continue to be validated at that level in subsequent years.” ([Security Assessment](https://support.google.com/cloud/answer/13465431)). ADA’s older CASA-start note says the same for legacy “tier 3” ([CASA Framework User Initiated Assessment](https://appdefensealliance.dev/casa/casa-start)).

### AL1 vs AL2

Google: CASA “utilizes a risk-based, multi-tiered approach to evaluate application risk based on user count, requested scopes, and other application-specific signals. Applications are assigned to either the AL1 or AL2 assurance level.” The required level “is dynamic and may increase based on changes in your user base or data-handling practices.” ([Security Assessment](https://support.google.com/cloud/answer/13465431))

ADA: “The framework users (Google..etc) and not the application developer calculate and determine which assurance level is required.” Inputs ADA recommends: data sensitivity, number of users per data type, company risk tolerance, external/internal risk indicators. **All requirements must be satisfied at every level; only the assessment method changes.** ([Assurance Levels](https://appdefensealliance.dev/casa/casa-tiering))

Google FAQ (still using “tier” language in places): application tier is calculated from data sensitivity, users per data type, and internal risk indicators; the tier **can change** ([OAuth verification FAQ](https://support.google.com/cloud/answer/13463817)).

ADA CASA Specification v2.1.1 (2026-06-03) definitions ([CASA Specification](https://github.com/appdefensealliance/ASA-WG/blob/main/CASA/CASA%20Specification.md)):

- **AL1 (Verified Self Assessment):** “The developer provides evidence and statements of compliance to each audit test case. The ADA approved lab reviews the evidence against the requirements. The ADA approved lab does not directly assess the application.”
- **AL2 (Lab Assessment):** “The ADA approved lab evaluates each audit test case directly against the application. In some cases, the developer may need to provide limited information or code snippets.”

ADA’s assurance-level page describes AL2 as testing “the application, the application deployment infrastructure and any user data storage location” ([Assurance Levels](https://appdefensealliance.dev/casa/casa-tiering)). Google’s FAQ for legacy “Tier 3” says the assessor needs read-only access to the cloud system where Google production data is stored, or else onsite / screen-share review, “which will take more time and therefore will be a more costly assessment” ([OAuth verification FAQ](https://support.google.com/cloud/answer/13463817)).

Which AL this app will be assigned is **not published as a formula**. Google decides after looking at scopes, user counts, and other signals. A restricted Drive scope plus server-side storage is enough to *require CASA*; it is not enough to predict AL1 vs AL2 from the docs.

### What CASA / Google verification asks of a **public** repository

Google and ADA **do not** require the GitHub repository to be private. They also **do not** say that a public repo is forbidden.

What they do require:

| Requirement | What the source says | Source |
| --- | --- | --- |
| Homepage | Publicly accessible; not only a login page; hosted on a verified domain you own; describes functionality; links the same privacy policy as the consent screen | [Restricted scope verification — Application home page requirements](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [Verification requirements](https://support.google.com/cloud/answer/13464321); [Manage OAuth App Branding](https://support.google.com/cloud/answer/10311615) |
| Privacy policy | Visible; hosted on the same domain as the homepage; linked from the consent screen; discloses how the app accesses, uses, stores, or shares Google user data; Limited Use compliant | same pages; [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy) |
| Domain ownership | Authorized domains verified in Search Console by a project Owner or Editor | [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [Verification requirements](https://support.google.com/cloud/answer/13464321) |
| Demo video | Unlisted YouTube; English consent flow; app name; OAuth client ID in the address bar; each requested sensitive/restricted scope used in-product | [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [Verification requirements](https://support.google.com/cloud/answer/13464321) |
| Data deletion | Security assessment verifies the app can “delete user data upon a user's request.” Workspace policy: “Honor user requests to delete their data.” Apps must provide help docs on how users manage and delete their data. | [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [Google Workspace user data and developer policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy) |
| Limited Use statement | Affirmative statement that use of Google Workspace data adheres to Limited Use, e.g. on the homepage or privacy policy | [Google Workspace user data and developer policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy); [OAuth verification FAQ](https://support.google.com/cloud/answer/13463817) |
| Source code for CASA | ADA definition of “Code snippets”: “The full source code, calling functions or underlying libraries do not need to be included.” AL2 may request “limited information or code snippets.” ADA Tier 2 complete-submit: “No application code, scan results, or vulnerability findings are shared or disclosed to Google as part of verification.” TAC (listed assessor) describes a local Fluid Attacks scan whose **CSV output** is shared, as an alternative to uploading source. | [CASA Specification](https://github.com/appdefensealliance/ASA-WG/blob/main/CASA/CASA%20Specification.md); [Complete your CASA](https://appdefensealliance.dev/casa/tier-2/complete-submit); [TAC CASA FAQs](https://tacsecurity.com/esof-appsec-ada-casa-faqs/) |

**Not found in a primary source:** a Google or ADA rule that a public GitHub repo must be made private, or that source must be disclosed to Google, for Drive restricted-scope verification.

A public repo still means the implementation is world-readable. That is an engineering/security fact, not a Google verification rule.

---

## 4. Domain-wide delegation, admin-trusted apps, internal apps

### Domain-wide delegation (service account + admin install of scopes)

**What it is.** A Workspace super admin authorizes a service account’s client ID plus a comma-delimited list of OAuth scopes in Admin Console → Security → Access and data control → API controls → Domain-wide delegation. The app then impersonates users in that domain. Google’s example even uses `https://www.googleapis.com/auth/drive` as a sample scope string ([Using OAuth 2.0 for Server to Server Applications](https://developers.google.com/identity/protocols/oauth2/service-account)).

**Does it change the scope?** No. The admin still grants the same scope URIs (`drive.readonly`, etc.). Access is the intersection of those scopes and what the impersonated user can access ([Using OAuth 2.0 for Server to Server Applications](https://developers.google.com/identity/protocols/oauth2/service-account)).

**Does it change verification?** Domain-wide *delegation* is not the same exception as domain-wide *installation*. Google’s verification exception for “Domain-wide installation” is: if the app **only** targets Workspace/Cloud Identity users **and always uses domain-wide installation**, brand verification is not required, **but** “if your app utilizes restricted or sensitive scopes, app verification is required” ([Restricted scope verification — Domain-wide installation](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)).

Google’s Workspace-specific verification page: DWD “does not change token lifetimes” but “allows administrators to pre-authorize apps, bypassing user consent and directly managing the app's access to organization data” ([Additional considerations for Google Workspace](https://developers.google.com/identity/protocols/oauth2/production-readiness/google-workspace)).

**Does it skip CASA?** Not found in a primary source that DWD, by itself, exempts a multi-tenant public app from CASA. CASA is triggered by restricted scopes plus server-side access to user data ([Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)). The documented exception is **internal use within the developer’s own organization**, not “any customer who grants DWD.”

**DWD cannot be used for consumer Gmail accounts.** Service-account domain-wide authority is a Workspace admin feature ([Using OAuth 2.0 for Server to Server Applications](https://developers.google.com/identity/protocols/oauth2/service-account)).

### Internal apps (User type = Internal)

This is the exception that **does** skip Google verification **for the developer’s own org**:

- The Cloud project must be owned by the organization.
- OAuth consent user type must be **Internal**.
- Only members of that Google Workspace / Cloud Identity organization can authorize.
- “Your app will not be subject to the unverified app screen or the 100-user cap if it's designated as internal-only.” ([When is verification not needed](https://support.google.com/cloud/answer/13464323); [Restricted scope verification — Internal use only](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview))
- “For apps used only internally by your Google Workspace organization, scopes aren't listed on the consent screen and use of restricted or sensitive scopes doesn't require further review by Google.” ([Configure the OAuth consent screen](https://developers.google.com/workspace/guides/configure-oauth-consent))
- Workspace policy: “If an app is only used by users within your own organization, then these additional requirements do not apply.” ([Google Workspace user data and developer policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy))

This is **one Cloud organization = one Workspace**. A public SaaS whose customers are *other* companies cannot set User type = Internal for those customers. `org_internal` is returned if someone outside the parent org tries to authorize ([Manage App Audience](https://support.google.com/cloud/answer/15549945)).

Workspace admins can also check **Trust internal apps** so internal apps can access restricted Google Workspace APIs ([Control which apps access Google Workspace data](https://support.google.com/a/answer/7281227)). That setting is about *that organization’s own* internal apps.

### Admin-trusted / Marketplace-installed apps

Google lists “Google Workspace admin-trusted or marketplace-installed apps” as a case where verification is not *mandatory for use inside that domain*:

- An admin can add a third-party app to the trusted-apps list. Users who do not already have the app can install it whether or not it is verified.
- Admins can admin-install an unverified Marketplace app; Google discloses unverified status, but access is granted to users who have the admin-installed app.
([When is verification not needed](https://support.google.com/cloud/answer/13464323))

“Trusted” in the Admin console: the app “has access to all Google Workspace services (OAuth scopes), including restricted services.” Drive `drive.readonly` is on the Admin console high-risk Drive list; if the admin restricts Drive as a service, only Trusted (or “Specific Google data”) apps get that data ([Control which apps access Google Workspace data](https://support.google.com/a/answer/7281227)).

Google’s OAuth state overview: when an admin marks an app Trusted, “it is treated as an internal application for that organization. This status overrides certain standard OAuth limitations for the organization's users, such as the 100-test-user cap and the 7-day refresh token expiration limit for apps in the Testing status.” Admins can still Block any app. Unverified external apps “are unlikely” to be trusted; marking an unverified app Trusted “is generally discouraged.” ([OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview))

**Trusted does not replace Google verification for a public External app** that also serves Gmail users and other domains. It is a *per-customer admin override* for that Workspace.

### Issue #2: what this constrains

[Issue #2](https://github.com/DennieDan/knowledge-graph/issues/2) asks for individual-account and Google Workspace user flows. The scope/verification facts that constrain those flows:

| Flow | Identity | Drive access | Verification / caps |
| --- | --- | --- | --- |
| **Individual Gmail** | Per-user Google Sign-In (`openid` / `email` / `profile`) | Per-user OAuth for `drive.readonly`. No DWD. No Internal user type. | Testing: 100 named test users, tester warning, 7-day refresh tokens. Published unverified: danger UI + lifetime 100-user cap. Production at 10–100-person companies requires **verified** `drive.readonly`. |
| **Workspace, per-user (default MVP)** | Same Sign-In | Same `drive.readonly` user OAuth | Same Google verification for the *app*. Each customer’s admin may still **Block**, **Limit**, or require **Trusted** before high-risk Drive scopes work. Publish the OAuth client ID in admin docs ([Additional considerations for Google Workspace](https://developers.google.com/identity/protocols/oauth2/production-readiness/google-workspace)). |
| **Workspace, admin-trusted** | Same Sign-In | Same scope; admin allowlists the client ID | Can override the 100-user / 7-day testing limits **for that org only**. Does not verify the app for Gmail users or other domains. |
| **Workspace, domain-wide delegation** | Service account impersonates each user | Same `drive.readonly` string in the DWD grant | Skips per-user consent in that domain. Does not change the scope. Does not, per available Google docs, skip restricted-scope verification/CASA for a public multi-tenant app. Impossible for consumer Gmail. |
| **Internal-only (developer’s own Workspace)** | Internal user type | Same scope, no Google review | Only the developer’s org. Cannot ship this as the product for Singapore customers on mixed Gmail + Workspace. |

---

## 5. What can an unverified app do? Can the team build now?

**Yes. Google says so in those words:** “You can continue to build and test your app while waiting to complete verification.” “Apps in development: if your app is experimental or a test build, you don't need to go through verification unless you decide to launch it to the public.” ([Unverified apps](https://support.google.com/cloud/answer/7454865))

Development/testing/staging projects “are not subject to verification.” Google recommends separate Cloud projects for test vs production, and submitting only the production project ([When is verification not needed](https://support.google.com/cloud/answer/13464323); [Restricted scope verification — Development, Testing, or Staging](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)).

### Testing publishing status (the right way to build now)

From [Manage App Audience](https://support.google.com/cloud/answer/15549945) and [OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview):

- **Up to 100 test users** on the OAuth consent screen. “A test user consumes a project's test user quota once added to the project.”
- Only those listed accounts can authorize (exception: if the app requests **only** `openid` / `email` / `profile` / `userinfo.*`, any user can sign in, with no warning and no 7-day expiry). Adding `drive.readonly` **removes** that exception.
- Google shows a **warning** that the user has test access and should consider the risks of an unverified app.
- Authorizations by a test user **expire seven days** from consent; the refresh token expires too if `access_type=offline`.
- Workspace users are **not** exempt from Testing rules unless User type is Internal.
- A Workspace admin who marks the app **Trusted** overrides the 100-test-user cap and the 7-day refresh-token limit **for that organization’s users**.

### Published but unverified (do not use this as the launch path)

- Any Google Account can try to authorize.
- App name and logo are **not** shown until brand verification ([OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview); [Manage OAuth App Branding](https://support.google.com/cloud/answer/10311615)).
- Sensitive/restricted scopes show the **unverified app / “Danger UI”** screen.
- **New user cap: 100 new users in total after the unverified-app screen is presented.** The cap “applies over the entire lifetime of the project, and it cannot be reset or changed.” Appeal path: request verification. ([Unverified apps](https://support.google.com/cloud/answer/7454865); [Manage App Audience](https://support.google.com/cloud/answer/15549945))
- Google’s state overview calls published+unverified “Strongly discouraged” and states a “hard cap of 100 total users” for sensitive/restricted ([OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)).
- Exhausting the cap can disable Google sign-in for the project ([OAuth verification FAQ](https://support.google.com/cloud/answer/13463817)).

### What “unverified” is

“An unverified app is an app or Apps Script that requests a sensitive or restricted OAuth scope, but hasn't gone through the Google verification process.” The unverified-app screen appears when those scopes are requested and not (yet) approved, including while verification is in progress ([Unverified apps](https://support.google.com/cloud/answer/7454865)).

### Practical build-now setup

1. Cloud project **Audience = External**, **Publishing status = Testing**.
2. Add the team and a small set of design-partner Google accounts (Gmail and Workspace) as test users — stay under 100.
3. Request `openid` / `email` / `profile` + `drive.readonly`.
4. Expect tester warnings and weekly re-consent until you verify.
5. Keep a **separate** production project for the verification submission ([When is verification not needed](https://support.google.com/cloud/answer/13464323); [Requesting Minimum Scopes](https://support.google.com/cloud/answer/13807380) also says not to call unapproved scopes from production code).

Google Sign-In as identity does not require Drive verification by itself. The Drive connector does.

---

## 6. How to read a file’s sharing permissions to mirror them

### API

Use **`permissions.list`**:

`GET https://www.googleapis.com/drive/v3/files/{fileId}/permissions`

([permissions.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/list); conceptual guide [Share files, folders, and drives](https://developers.google.com/workspace/drive/api/guides/manage-sharing))

Google calls the full list of permission resources on a file, folder, or shared drive the **ACL** ([Share files, folders, and drives](https://developers.google.com/workspace/drive/api/guides/manage-sharing)).

### Fields you must request

“By default, permission requests only return a subset of fields. Permission `kind`, `ID`, `type`, and `role` are always returned. To retrieve specific fields, see Return specific fields.” ([REST Resource: permissions](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions))

The sharing guide: `list` by default returns only `id`, `type`, `kind`, and `role`. To get `permissionDetails`, set `fields=permissions/permissionDetails` ([Share files, folders, and drives](https://developers.google.com/workspace/drive/api/guides/manage-sharing)).

Fields on the [Permission resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions) that matter for a mirror:

| Field | Meaning (quoted / paraphrased from the resource doc) |
| --- | --- |
| `id` | Opaque permission ID; published on the User resource as `permissionId` |
| `type` | `user`, `group`, `domain`, or `anyone` |
| `role` | `owner`, `organizer`, `fileOrganizer`, `writer`, `commenter`, `reader` |
| `emailAddress` | User or group email |
| `displayName` | Pretty name (empty for `anyone`) |
| `domain` | Domain for `type=domain` |
| `allowFileDiscovery` | Whether `domain` / `anyone` links are discoverable via search |
| `expirationTime` | RFC 3339 expiry (user and group only; max one year ahead) |
| `deleted` | Whether the user/group account was deleted |
| `pendingOwner` | Pending owner; “only populated for permissions of type `user` for files that aren't in a shared drive” |
| `permissionDetails[]` | Inherited vs direct; see below |
| `inheritedPermissionsDisabled` | When true, only organizers/owners and directly added users can access |

### Do not rely on `files.permissions[]` for shared drives

The File resource field `permissions[]` is: “The full list of permissions for the file. This is only available if the requesting user can share the file. **Not populated for items in shared drives.**” ([files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)). `owners[]` is also “isn't populated for items in shared drives.” Use `permissions.list` with `supportsAllDrives=true`.

`permissionIds[]` on the File resource is a list of permission IDs with access, but it is not a full ACL ([files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)).

### Shared drives vs My Drive

| Topic | What Google documents |
| --- | --- |
| Enable shared drives on requests | `supportsAllDrives=true` on `permissions.list` / `files.get`; `includeItemsFromAllDrives=true` on `files.list` / `changes.list` ([permissions.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/list); [files.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list); [changes.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/changes/list)) |
| Pagination | Shared drives: default page size 100, max 100. Non-shared drives: if `pageSize` unset, “the entire list of permissions” is returned ([permissions.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/list)) |
| Admin listing of a shared drive | `useDomainAdminAccess=true` only if `fileId` is a shared drive and the requester is an admin of that domain ([permissions.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/list)) |
| Role source on shared drives | Call `permissions.get` with `fields=permissionDetails`. `permissionDetails[].permissionType` is `file` or `member`. `inheritedFrom` is “the ID of the item from which this permission is inherited. **This is only populated for items in shared drives.**” `inherited` “is always populated.” ([permissions resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions); [Share files, folders, and drives — Determine the role source](https://developers.google.com/workspace/drive/api/guides/manage-sharing)) |
| Direct vs inherited on shared drives | `hasAugmentedPermissions`: “Whether there are permissions directly on this file. This field is only populated for items in shared drives.” ([files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)) |
| My Drive owners | `owners[]` populated; not populated for shared-drive items ([files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)) |

### Inherited permissions (how they propagate)

From [Share files, folders, and drives — How permissions propagate](https://developers.google.com/workspace/drive/api/guides/manage-sharing):

- “Inherited by default: All child files and folders automatically inherit permissions from their parent folder.”
- “Cannot be reduced on children: You cannot remove or reduce an inherited permission on a child item. Changes must be made on the originating parent, or the folder must use the limited access setting.”
- “Can be expanded on children: A child item can grant a more permissive role…”
- “Re-evaluated on move: Moving an item to a new parent folder re-evaluates and applies the new parent's permissions to the item and its children.”

Limited access: File field `inheritedPermissionsDisabled` — “When `true`, only organizers, owners, and users with permissions added directly on the item can access it.” ([permissions resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions); [files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files))

For a Postgres mirror: persist each `permissions.list` row (grantee, role, direct vs inherited, `inheritedFrom` when present), and treat parent-folder ACLs as the source of inherited rows. On `changes.watch` notifications with `X-Goog-Changed: permissions`, re-list that file’s permissions. Because inheritance is re-evaluated on move, also re-list after parent changes (`X-Goog-Changed` can include `parents`).

### Capabilities vs ACL

Google: the `permissions` resource is the ACL (who has access). It “does not directly indicate whether the current user can perform a specific action.” The File `capabilities` booleans (`canComment`, `canShare`, `canDelete`, …) are computed for the *current user*. For UI, Google says to read `files.capabilities`, not to parse permissions ([Share files, folders, and drives — Understand file capabilities](https://developers.google.com/workspace/drive/api/guides/manage-sharing); [Manage file metadata](https://developers.google.com/workspace/drive/api/guides/file-metadata)). A **sharing mirror** needs the ACL (`permissions.list`), not only capabilities.

---

## Comparison table of scopes

| Scope | Official description (Drive guide / catalog) | Google classification | File **content** (`files.get alt=media`, `files.export`) | Sharing ACL (`permissions.list`) | Live change feed (`changes.watch` / `changes.list`) | File coverage | Writes Drive files? | Verification if used on a public External app with server-side storage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `drive.readonly` | “View and download all your Drive files” / “See and download all your Google Drive files” | **Restricted** | Yes. `files.export` lists this scope. | Yes | Yes | All files the user can access (My Drive + shared, with `supportsAllDrives`) | No (read/download only) | Brand + restricted verification + CASA |
| `drive.metadata.readonly` | “View metadata for files in your Drive” / “See information about your Google Drive files” | **Restricted** | **No.** Metadata scopes “strictly prohibit access to file content.” `files.export` does not list this scope. | Yes | Yes (metadata events) | All files’ metadata | No | Still Restricted + CASA if stored on servers — and it cannot satisfy “read files” |
| `drive.file` | “Create new Drive files, or modify existing files, that you open with an app or that the user shares with an app…” / “See, edit, create, and delete only the specific Google Drive files you use with this app” | **Non-sensitive** | Yes, **only** for files in the app’s grant set | Yes, **only** for those files | Yes, **only** for those files | Picker / Open with / created-by-app | **Yes** (edit/create/delete on those files) | Basic brand verification; no restricted CASA *for this scope*. Does not cover whole-Drive live sync |
| `drive` (full) | “View and manage all your Drive files” / “See, edit, create, and delete all of your Google Drive files” | **Restricted** | Yes | Yes | Yes | All files | **Yes** (including delete and share) | Brand + restricted + CASA. Broader than needed; Google tells reviewers to downscope |
| `drive.activity.readonly` | “View the activity record of files in your Drive” | **Restricted** | No (Activity API, not file bytes) | No (not a permissions.list scope) | Not the Changes API; query past activity | Activity records | Can be read-only | Extra restricted scope. Not required for `changes.watch` live sync |
| `openid` `email` `profile` | Google Sign-In / OpenID Connect identity | Non-sensitive (pre-filled) | No | No | No | n/a | No | Not Drive verification. Testing-mode 100-user / 7-day limits do **not** apply if these are the **only** scopes |

Scope description sources: [Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [OAuth 2.0 Scopes for Google APIs](https://developers.google.com/identity/protocols/oauth2/scopes). Method sources are linked in §1.

---

## 7. Recommendation: MVP scope set, verification path, Gmail vs Workspace

### Commit to this scope set

```
openid
email
profile
https://www.googleapis.com/auth/drive.readonly
```

Optional later, **not** MVP:

- `drive.activity.readonly` — only if the product must show “who changed what,” which is a second Restricted scope and a second API ([activity.query](https://developers.google.com/workspace/drive/activity/v2/reference/rest/v2/activity/query)).
- `drive.file` — only if a *separate* “user picked these files” path is added. It cannot replace `drive.readonly` for whole-Drive mirror, and it grants write on picked files.

Do not add `drive` (full). Google’s minimum-scope policy requires the narrowest scope that implements the feature, and forbids requesting scopes for unimplemented future work ([Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy); [Verification requirements — Request narrowest scopes](https://support.google.com/cloud/answer/13464321); [Requesting Minimum Scopes](https://support.google.com/cloud/answer/13807380)).

### Verification path: build now / verify later

1. **Now:** Testing project, ≤100 test users, implement `files.list` / `files.get` / `files.export` / `permissions.list` / `changes.watch` + `changes.list` with `supportsAllDrives`. Google explicitly allows building while unverified ([Unverified apps](https://support.google.com/cloud/answer/7454865)).
2. **Before any non-test customer launch:** production Cloud project, External user type, brand verification (homepage, privacy policy, Search Console domain, demo video), then restricted-scope verification with a justification that Picker/`drive.file` cannot list or watch the user’s Drive or mirror inherited ACLs, then CASA when Trust & Safety says to start it ([Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification); [Security Assessment](https://support.google.com/cloud/answer/13465431)).
3. **Plan ~6 weeks** of restricted verification plus assessor lead time, unguaranteed ([OAuth verification FAQ](https://support.google.com/cloud/answer/13463817)). Do not wait for CASA to start writing the connector.
4. **Annually:** CASA recertification from LOV date ([Annual Recertification](https://support.google.com/cloud/answer/13463816)).

### What this implies for individual Gmail vs Workspace (issue #2)

- **Same Drive scope in both flows.** Admins and DWD do not get a narrower or different Drive scope for this product.
- **Gmail users** must complete per-user OAuth and live with unverified warnings until the app is verified. There is no admin Trust escape hatch. The 100-user cap is a hard launch blocker for a 10–100 person company if the app is still unverified.
- **Workspace users** use the same per-user OAuth for MVP. Document the OAuth client ID so customer admins can mark the app Trusted or allow high-risk Drive scopes ([Additional considerations for Google Workspace](https://developers.google.com/identity/protocols/oauth2/production-readiness/google-workspace); [Control which apps access Google Workspace data](https://support.google.com/a/answer/7281227)).
- **Do not** design the public product as User type = Internal. That only works inside *your* Cloud organization ([When is verification not needed](https://support.google.com/cloud/answer/13464323)).
- **DWD** is an optional Workspace-only convenience (admin grants `drive.readonly` once; app impersonates members). Keep it off the MVP critical path. It does not help Gmail-only companies in the Singapore mix.

---

## Open risks / things Google docs leave ambiguous

1. **Will Google accept `drive.readonly` for this product, or demand `drive.file`?** Reviewer help tells teams to use `drive.file` when the feature is upload/download/delete of *specific* files, and `drive.readonly` only when Picker “justifiably does not fit” ([Requesting Minimum Scopes](https://support.google.com/cloud/answer/13807380)). A live ACL+content mirror is the latter, but Google’s reviewers decide. No public rubric guarantees approval.
2. **Which CASA assurance level Google will assign** is not a published function of “Drive readonly + N users.” Google/ADA say Google calculates AL from sensitivity, user count, and other signals ([Security Assessment](https://support.google.com/cloud/answer/13465431); [Assurance Levels](https://appdefensealliance.dev/casa/casa-tiering)).
3. **CASA dollar cost** is not owned by Google or ADA. Only some listed assessors publish prices; others do not. Quotes may fall outside USD 675–6,000.
4. **End-to-end calendar time** is not a single official number. Google’s FAQ says 6 weeks for restricted verification and also that estimates are not guaranteed; unverified-apps help mentions “several months” for some apps ([OAuth verification FAQ](https://support.google.com/cloud/answer/13463817); [Unverified apps](https://support.google.com/cloud/answer/7454865)).
5. **Public GitHub vs CASA source handling.** ADA says full source need not be included and is not disclosed to Google; some assessor workflows still ask for a zip or a local scan artifact ([CASA Specification](https://github.com/appdefensealliance/ASA-WG/blob/main/CASA/CASA%20Specification.md); [Complete your CASA](https://appdefensealliance.dev/casa/tier-2/complete-submit)). Whether a public repo is treated as extra risk during AL assignment is **not stated**.
6. **`files.get` lists `drive.metadata.readonly` as an authorized scope** ([files.get](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get)) **and** the metadata guide says download is blocked for that scope ([Manage file metadata](https://developers.google.com/workspace/drive/api/guides/file-metadata)). Treat `alt=media` as unsupported under metadata-only; do not plan on it.
7. **`permissionDetails.inheritedFrom` is documented only for shared drives** ([permissions resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions)). How to reconstruct the *parent folder id* for inherited My Drive ACLs from `permissions.list` alone is not spelled out. The propagation rules are documented; a dedicated “inheritedFrom on My Drive” field is not.
8. **`files.permissions[]` is omitted on shared drives and when the current user cannot share** ([files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)). A mirror that only reads File.permissions will be silently incomplete.
9. **Domain-wide installation vs domain-wide delegation.** Google’s verification exception is written for Marketplace-style domain-wide *installation*. DWD is documented as an admin pre-authorization mechanism. Whether a DWD-only, Workspace-only SKU could skip *brand* verification is suggested by the “always use domain-wide installation” exception, but that exception still requires app verification for restricted scopes ([Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)). A mixed Gmail+Workspace launch cannot rely on it.
10. **Admin “Trusted” vs Google “Verified.”** Trusted is per-domain and discouraged for unverified apps ([OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)). It is not a substitute for Google verification when selling to many companies and Gmail users.
11. **Limited Use and AI.** Workspace policy prohibits using Google user data “to create, train, or improve a machine learning or artificial intelligence model beyond that specific user’s personalized model” ([Google Workspace user data and developer policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy); [OAuth verification FAQ](https://support.google.com/cloud/answer/13463817)). How a knowledge-graph product is classified under that sentence is a policy-review question, not something the API docs settle.
12. **Naming drift.** Google Help still says LOV, LOA, Tier 2, Tier 3, AL1, and AL2 in different articles. ADA’s current spec uses AL1/AL2 ([CASA Specification](https://github.com/appdefensealliance/ASA-WG/blob/main/CASA/CASA%20Specification.md)). Treat “Tier 2 ≈ AL1 (lab-reviewed evidence)” and “Tier 3 ≈ AL2 (lab-tested)” as the mapping ADA/Google describe, not as a separately numbered Google product.

---

## Primary sources (index)

Drive scopes and methods

- [Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [OAuth 2.0 Scopes for Google APIs](https://developers.google.com/identity/protocols/oauth2/scopes)
- [Requesting Minimum Scopes](https://support.google.com/cloud/answer/13807380)
- [Restricted Scopes (Cloud Help)](https://support.google.com/cloud/answer/13464325)
- [files.get](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get) · [files.export](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/export) · [files.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list) · [files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)
- [permissions.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/list) · [permissions resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions) · [Share files, folders, and drives](https://developers.google.com/workspace/drive/api/guides/manage-sharing)
- [Manage file metadata](https://developers.google.com/workspace/drive/api/guides/file-metadata)
- [changes.watch](https://developers.google.com/workspace/drive/api/reference/rest/v3/changes/watch) · [changes.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/changes/list) · [files.watch](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/watch) · [Notifications for resource changes](https://developers.google.com/workspace/drive/api/guides/push)
- [Drive Activity activity.query](https://developers.google.com/workspace/drive/activity/v2/reference/rest/v2/activity/query)

Verification, unverified apps, Workspace exceptions

- [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- [OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)
- [Additional considerations for Google Workspace](https://developers.google.com/identity/protocols/oauth2/production-readiness/google-workspace)
- [Configure the OAuth consent screen](https://developers.google.com/workspace/guides/configure-oauth-consent)
- [Unverified apps](https://support.google.com/cloud/answer/7454865)
- [Manage App Audience](https://support.google.com/cloud/answer/15549945)
- [When is verification not needed](https://support.google.com/cloud/answer/13464323)
- [OAuth verification FAQ](https://support.google.com/cloud/answer/13463817)
- [Verification requirements](https://support.google.com/cloud/answer/13464321)
- [Manage OAuth App Branding](https://support.google.com/cloud/answer/10311615)
- [Control which apps access Google Workspace data](https://support.google.com/a/answer/7281227)
- [Using OAuth 2.0 for Server to Server Applications](https://developers.google.com/identity/protocols/oauth2/service-account)

Policy

- [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)
- [Google Workspace user data and developer policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)
- [Google Drive API Terms of Service](https://developers.google.com/workspace/drive/api/terms)

CASA / assessors

- [Security Assessment (Cloud Help)](https://support.google.com/cloud/answer/13465431)
- [Annual Recertification](https://support.google.com/cloud/answer/13463816)
- [CASA overview (ADA)](https://appdefensealliance.dev/casa/casa-beta)
- [CASA assurance levels (ADA)](https://appdefensealliance.dev/casa/casa-tiering)
- [CASA Framework User Initiated Assessment (ADA)](https://appdefensealliance.dev/casa/casa-start)
- [Complete your CASA (ADA)](https://appdefensealliance.dev/casa/tier-2/complete-submit)
- [CASA Specification v2.1.1 (ADA / ASA-WG)](https://github.com/appdefensealliance/ASA-WG/blob/main/CASA/CASA%20Specification.md)
- [TAC Security CASA](https://tacsecurity.com/google-casa-cloud-application-security-assessment/) · [TAC CASA FAQs](https://tacsecurity.com/esof-appsec-ada-casa-faqs/)
- [Leviathan CASA](https://www.leviathansecurity.com/programs/google-casa-cloud-application-security-assessment)
