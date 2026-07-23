from __future__ import annotations

"""Legal page copy for the public Mparanza site."""

from typing import Any

__all__ = [
    "CONTACT_EMAIL",
    "LEGAL_EFFECTIVE_DATE",
    "LEGAL_PAGES",
    "SUPPORT_EMAIL",
    "get_legal_page",
]

CONTACT_EMAIL = "fabio@mparanza.com"
SUPPORT_EMAIL = "fabio@mparanza.com"
LEGAL_EFFECTIVE_DATE = "July 23, 2026"

LEGAL_PAGES: dict[str, dict[str, Any]] = {
    "zero-retention": {
        "title": "Zero Retention Policy",
        "eyebrow": "Mparanza LLC · Privacy notice",
        "effective_date": LEGAL_EFFECTIVE_DATE,
        "summary": (
            "Mparanza's products use two processing categories. Ordinary plugin "
            "functions use your existing ChatGPT plan and Codex workspace. "
            "Mparanza does "
            "not receive or retain Customer Content merely because you use those "
            "functions, and the plugin does not automatically anonymize that "
            "content. Mparanza-hosted services receive the content needed to "
            "provide them under the retention rules below."
        ),
        "sections": [
            {
                "id": "commitment",
                "title": "What Zero Retention Means",
                "paragraphs": [
                    (
                        "Zero retention is a design objective for Customer Content "
                        "on systems that Mparanza controls, not a claim that every "
                        "hosted service stores nothing. Customer Content means files, "
                        "datasets, prompts, instructions, recordings, transcripts, "
                        "reports, comments, and workflow outputs submitted for processing."
                    ),
                    (
                        "Ordinary plugin functions use your existing ChatGPT plan and "
                        "Codex workspace without sending Customer Content to Mparanza. "
                        "Mparanza-hosted services receive the content described for each "
                        "service and follow the retention and deletion arrangements below."
                    ),
                    (
                        "Authentication, delivery, security, legal, saved-service, "
                        "and external-service records are also addressed below."
                    ),
                ],
            },
            {
                "id": "scope",
                "title": "Scope",
                "paragraphs": [
                    (
                        "This policy applies to mparanza.com, Mparanza-hosted "
                        "tools, downloadable plugins, authentication and download "
                        "flows, support communications, and other Mparanza services "
                        "that link to it. It explains both retention and the wider "
                        "handling of personal information."
                    ),
                    (
                        "Mparanza-controlled systems are systems that Mparanza "
                        "operates or can directly administer. Your own device, "
                        "existing ChatGPT plan and Codex workspace, connected "
                        "services, email provider, "
                        "and other externally operated systems are not "
                        "Mparanza-controlled systems."
                    ),
                    (
                        "If you use Mparanza for an organization, you are "
                        "responsible for giving required notices and obtaining "
                        "the rights and permissions needed for information you "
                        "choose to process."
                    ),
                ],
            },
            {
                "id": "local-plugins",
                "title": "Ordinary Plugin Functions",
                "paragraphs": [
                    (
                        "Ordinary plugin functions use your existing ChatGPT plan "
                        "and Codex workspace. Files, scripts, and outputs "
                        "may stay on your computer, while content Codex reads can "
                        "enter the model context under that plan. Mparanza does not "
                        "receive, access, or retain that Customer Content merely "
                        "because you use the plugin, and the plugin does not "
                        "automatically anonymize it."
                    ),
                    (
                        "Your ChatGPT plan, Codex workspace settings, connectors, and "
                        "other services process information under their own "
                        "arrangements. If a plugin clearly invokes a Mparanza-hosted "
                        "service, that category is covered by the next section."
                    ),
                    (
                        "A public Plugins Directory listing is only a distribution and "
                        "discovery surface. Vera and Clara workflows stop on ChatGPT web "
                        "and mobile and require Codex Desktop. The user's existing "
                        "ChatGPT plan may still govern the model context inside Codex."
                    ),
                    (
                        "Vera's Studio Archive uses two non-hosted message routes. "
                        "Gmail is searched only from Codex Desktop through OpenAI's "
                        "separately connected Gmail connector. WhatsApp is inspected "
                        "only from Codex Desktop with Computer Use in the WhatsApp "
                        "Desktop app already opened and authenticated by the "
                        "professional. Neither route creates a Gmail or WhatsApp "
                        "message store on Mparanza-controlled systems. Screen text and "
                        "images read by Codex may still enter the model context under "
                        "the user's ChatGPT/Codex account."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Mparanza-Hosted Services",
                "paragraphs": [
                    (
                        "When you explicitly use a Mparanza-hosted service, the "
                        "content needed for that service reaches Mparanza-controlled "
                        "systems. Hosted processing may create uploads, temporary "
                        "files, session or job state, extracted content, generated "
                        "outputs, recordings, transcripts, or review artifacts."
                    ),
                    (
                        "Some hosted services process a request without intentionally "
                        "preserving durable feature state. Others intentionally "
                        "save a deck, template, checking session, interview, report, "
                        "or output so it can be resumed, reviewed, shared, retried, "
                        "or retrieved. Those saved records are exceptions to the "
                        "zero-retention objective until they are deleted."
                    ),
                    (
                        "Closing a browser, completing a job, archiving a project, "
                        "or allowing a link to expire does not necessarily delete "
                        "the underlying hosted data. Mparanza's product development "
                        "is focused on ordinary plugin functions and reducing these "
                        "hosted retention exceptions."
                    ),
                ],
            },
            {
                "id": "information-we-retain",
                "title": "Limited Information We Retain",
                "paragraphs": [
                    "Depending on how you use Mparanza, we may retain:",
                ],
                "bullets": [
                    (
                        "account and authentication information, such as your email "
                        "address and profile details used to sign in;"
                    ),
                    (
                        "Customer Content and feature state that you explicitly "
                        "submit to or create with a Mparanza-hosted service;"
                    ),
                    (
                        "limited download, transactional-message, and delivery "
                        "records, including email addresses or protected email "
                        "identifiers and relevant timestamps;"
                    ),
                    (
                        "communications, feedback, support requests, and other "
                        "messages you send to us; and"
                    ),
                    (
                        "technical and security information such as IP address, "
                        "browser information, request path, timestamps, cookie or "
                        "session identifiers, error logs, and security events."
                    ),
                ],
            },
            {
                "id": "how-we-use-information",
                "title": "How We Use Information",
                "paragraphs": [
                    "We use retained information for:",
                ],
                "bullets": [
                    "to perform the workflow or provide the feature you requested;",
                    (
                        "to authenticate users, secure sessions, prevent abuse, "
                        "and protect the Service;"
                    ),
                    ("to deliver requested downloads and transactional messages;"),
                    ("to troubleshoot failures and provide support; and"),
                    (
                        "to comply with law, enforce terms, and protect rights, "
                        "safety, and security."
                    ),
                ],
            },
            {
                "id": "uses-we-reject",
                "title": "Uses We Reject",
                "paragraphs": [
                    (
                        "Mparanza does not sell personal information, share it for "
                        "cross-context behavioral advertising, or use Customer "
                        "Content to train a generalized AI model. We do not claim "
                        "ownership of Customer Content."
                    ),
                    (
                        "Mparanza will not use Customer Content for a materially "
                        "different purpose unless that purpose is clearly disclosed "
                        "and separately authorized where required."
                    ),
                ],
            },
            {
                "id": "retention",
                "title": "Retention Today",
                "paragraphs": [
                    (
                        "Retention differs by service. The following describes the "
                        "current behavior:"
                    ),
                ],
                "bullets": [
                    (
                        "Ordinary plugin functions: Mparanza retention is zero for "
                        "content Mparanza does not receive. Content that Codex reads "
                        "is handled under the terms and data controls of your "
                        "existing ChatGPT plan and Codex workspace; local storage "
                        "is not anonymization."
                    ),
                    (
                        "Plugin updates and feedback: startup checks request the public "
                        "plugin-version manifest and may poll the status of a previously "
                        "submitted request. Those checks contain no Customer Content, "
                        "although the technical records described below may be logged. "
                        "Feedback or suggestion content is transmitted only through the "
                        "explicit submission workflow and remains a support record until "
                        "administrative deletion."
                    ),
                    (
                        "Request-scoped hosted tools: the application does not "
                        "intentionally preserve a durable feature copy after the "
                        "response, although temporary system handling and technical "
                        "logs may occur."
                    ),
                    (
                        "Check Entries: server working files are ordinarily removed "
                        "through periodic cleanup after about seven days; some job "
                        "metadata uses a shorter, event-triggered cleanup. Cleanup "
                        "is not guaranteed to occur at an exact instant."
                    ),
                    (
                        "Hosted Voice call capture: live video remains in the "
                        "browser and is not uploaded to Mparanza. Uploaded audio, "
                        "upload chunks, and transcription work files are deleted "
                        "before a completed package can be returned. On terminal "
                        "package retrieval, transcript and package job state are "
                        "scrubbed before the server sends the response; if that "
                        "scrub fails, retrieval is blocked. When an authenticated "
                        "launch includes compact case context, it is held in "
                        "owner-bound opaque-token metadata and used to guide "
                        "transcription. Token access expires after eight hours; "
                        "startup and periodic cleanup remove expired launch metadata "
                        "and abandoned call-capture state after interrupted processing."
                    ),
                    (
                        "Retail data bridge: Retailer Signals and Brand Fit evidence "
                        "jobs expire after 30 days, mapping worksets after 7 days, and "
                        "mapping submissions after 180 days. Product-image bytes and "
                        "generated reports are not uploaded by the plugin. These periods "
                        "cover bridge artifacts; central structured product records, "
                        "taxonomy, and accepted mappings are durable service data and do "
                        "not share that automatic schedule."
                    ),
                    (
                        "Saved Mparanza-hosted content: slide projects, templates, "
                        "and hosted interviews are retained until manual or "
                        "administrative deletion. Archiving a deck or expiration "
                        "of an interview link is not deletion."
                    ),
                    (
                        "Authentication: signed sessions normally expire after "
                        "12 hours. Sign-in links are single-use and normally expire "
                        "after 15 minutes, although related delivery and technical "
                        "records may remain separately."
                    ),
                    (
                        "Technical records: web access logs currently use 14 daily "
                        "rotations. Other application logs, download records, "
                        "message records, caches, exports, and backups do not yet "
                        "share one automatic deletion schedule and remain until "
                        "rotation, cleanup, or administrative deletion."
                    ),
                    (
                        "Diagnostic recording: where replay or diagnostic recording "
                        "is enabled for a hosted workflow, prompts and outputs may "
                        "remain until administrative deletion. Such a workflow is "
                        "not a zero-retention workflow."
                    ),
                ],
            },
            {
                "id": "external-services",
                "title": "External Services",
                "paragraphs": [
                    (
                        "Ordinary plugin functions use your existing ChatGPT plan "
                        "and Codex workspace. Mparanza does not control that plan or "
                        "workspace or make promises about its handling of data; its "
                        "terms and data controls apply separately."
                    ),
                    (
                        "When a Mparanza-hosted service uses an external service, the "
                        "content described for that hosted service may be transmitted "
                        "to it. External systems are not Mparanza-controlled systems, "
                        "and their terms apply separately."
                    ),
                    (
                        "For Studio Archive, OpenAI's Gmail connector accesses the "
                        "mailbox selected by the user inside Codex Desktop, while Codex "
                        "Desktop Computer Use can inspect the WhatsApp Desktop interface "
                        "on the user's own computer. Both routes execute only in Codex "
                        "Desktop. Gmail, WhatsApp, and OpenAI are external systems under "
                        "their own terms and controls. The professional signs in to "
                        "those services directly; Vera must not request passwords, QR "
                        "codes, authentication cookies, tokens, or one-time codes "
                        "through chat."
                    ),
                ],
            },
            {
                "id": "sharing",
                "title": "When Information May Be Shared",
                "paragraphs": [
                    "Mparanza may share information only:",
                ],
                "bullets": [
                    (
                        "with service providers and contractors as needed to "
                        "perform the purposes described in this policy;"
                    ),
                    (
                        "with your organization or workspace administrator when "
                        "you use an organization-controlled account or project;"
                    ),
                    (
                        "to comply with law, legal process, or an enforceable "
                        "request from a public authority;"
                    ),
                    ("to protect rights, property, security, or safety;"),
                    ("in connection with a corporate transaction; or"),
                    "with your consent or at your direction.",
                ],
            },
            {
                "id": "deletion-and-rights",
                "title": "Deletion Requests and Privacy Rights",
                "paragraphs": [
                    (
                        "You may ask Mparanza to identify, access, correct, or "
                        "delete information associated with you. We may verify "
                        "your identity and ask for the feature, approximate date, "
                        "or identifier needed to locate the information."
                    ),
                    (
                        "A deletion request covers Mparanza-controlled systems. "
                        "It does not remotely delete files in your workspace, "
                        "messages already delivered to recipients, recipient "
                        "copies, or information held in systems that Mparanza "
                        "does not control. Limited information may also be retained "
                        "where required for law, security, fraud prevention, or "
                        "the protection of another person's rights."
                    ),
                    (
                        "Depending on where you live, you may also have rights to "
                        "portability, restriction, objection, withdrawal of consent, "
                        "or appeal. Users in the EEA, UK, or Switzerland may complain "
                        "to their local data-protection authority. Applicable legal "
                        "bases may include performance of a contract, legitimate "
                        "interests, consent, and compliance with legal obligations."
                    ),
                    (
                        "For California residents, Mparanza does not sell personal "
                        "information or share it for cross-context behavioral "
                        "advertising."
                    ),
                ],
            },
            {
                "id": "security-and-transfers",
                "title": "Security and International Processing",
                "paragraphs": [
                    (
                        "We use administrative, technical, and organizational "
                        "measures designed to protect information. No online "
                        "service, transmission, storage system, or model-based "
                        "workflow can be guaranteed to be fully secure. Keep "
                        "independent copies of important content and secure your "
                        "account and devices."
                    ),
                    (
                        "Mparanza LLC is based in the United States. Hosted and "
                        "external-service processing may occur in the United States "
                        "and other countries whose data-protection laws differ from "
                        "those where you live."
                    ),
                ],
            },
            {
                "id": "children",
                "title": "Children",
                "paragraphs": [
                    (
                        "The Service is not directed to children under 18, and "
                        "we do not knowingly collect personal information from "
                        "children under 18. If you believe a child has provided "
                        "personal information to us, contact us so we can take "
                        "appropriate action."
                    ),
                ],
            },
            {
                "id": "changes",
                "title": "Changes",
                "paragraphs": [
                    (
                        "We may update this Zero Retention Policy as our workflows "
                        "and controls change. The effective date identifies the "
                        "current version. An updated version is effective when "
                        "posted unless it says otherwise, subject to applicable law."
                    ),
                ],
            },
            {
                "id": "contact",
                "title": "Contact",
                "paragraphs": [
                    (
                        "Zero-retention, deletion, and privacy requests should be "
                        f"sent to {CONTACT_EMAIL}."
                    ),
                ],
            },
        ],
    },
    "terms": {
        "title": "Terms of Service",
        "eyebrow": "Mparanza LLC",
        "effective_date": LEGAL_EFFECTIVE_DATE,
        "summary": (
            "These Terms govern access to and use of mparanza.com, Mparanza web "
            "tools, downloadable plugins, and related services. Ordinary plugin "
            "functions use your existing ChatGPT plan and Codex workspace, while "
            "Mparanza-hosted services have the data lifecycles described in the "
            "Zero Retention Policy. The Service is currently provided for free and "
            "without service levels."
        ),
        "sections": [
            {
                "id": "acceptance",
                "title": "Acceptance",
                "paragraphs": [
                    (
                        "By accessing or using the Service, you agree to these "
                        "Terms. If you use the Service on behalf of a company or "
                        "other organization, you represent that you have authority "
                        "to bind that organization, and the words you and your "
                        "include that organization."
                    ),
                    (
                        "If you do not agree to these Terms, you must not access "
                        "or use the Service."
                    ),
                ],
            },
            {
                "id": "free-service",
                "title": "Free Service",
                "paragraphs": [
                    (
                        "The Service is currently offered without charge. "
                        "Mparanza may add, change, restrict, suspend, discontinue, "
                        "or charge for any part of the Service at any time. The "
                        "Service is not a backup, archive, or permanent record "
                        "system. You are responsible for downloading requested "
                        "outputs and keeping independent copies you need."
                    ),
                    (
                        "There are no service levels, uptime commitments, support "
                        "commitments, backup or recovery commitments, availability "
                        "commitments, or professional-service commitments unless "
                        "Mparanza signs a separate written agreement. This concerns "
                        "preservation and availability; it does not alter the data-"
                        "handling commitments in the Zero Retention Policy."
                    ),
                ],
            },
            {
                "id": "accounts",
                "title": "Accounts and Access",
                "paragraphs": [
                    (
                        "You must provide accurate account information and keep "
                        "your sign-in credentials, email account, devices, and "
                        "sessions secure. You are responsible for activity under "
                        "your account, including activity by anyone who accesses "
                        "the Service through your account or device."
                    ),
                    (
                        "Mparanza may refuse, suspend, or terminate access at any "
                        "time, with or without notice, including if we believe "
                        "use of the Service may violate these Terms, create risk, "
                        "or expose Mparanza or others to liability."
                    ),
                ],
            },
            {
                "id": "user-content",
                "title": "User Content",
                "paragraphs": [
                    (
                        "You retain ownership of files, data, prompts, text, "
                        "records, instructions, comments, and other content you "
                        "provide, which these Terms call User Content. Content "
                        "processed by an ordinary plugin function through your "
                        "existing ChatGPT plan and Codex workspace is not submitted "
                        "to Mparanza "
                        "merely because the plugin reads or writes it. Mparanza "
                        "receives no license to that content unless you direct it "
                        "to a Mparanza-hosted service."
                    ),
                    (
                        "For User Content submitted to a Mparanza-hosted service, "
                        "you grant Mparanza and its service providers a limited, "
                        "worldwide, non-exclusive, royalty-free license to host, "
                        "copy, transmit, process, format, display to you, and "
                        "generate requested outputs from that content solely as "
                        "necessary to provide the requested feature, operate and "
                        "secure the Service, troubleshoot failures, enforce these "
                        "Terms, protect rights and safety, and comply with law. "
                        "This license lasts only for the applicable processing "
                        "and retention lifecycle."
                    ),
                    (
                        "You represent that you have all rights, notices, consents, "
                        "and legal bases required to submit User Content to the "
                        "Service and to permit its processing by Mparanza and "
                        "relevant service providers. You are responsible for User "
                        "Content and for keeping independent backups."
                    ),
                    (
                        "Mparanza does not acquire a right to sell User Content, "
                        "share it for cross-context behavioral advertising, or "
                        "use it to train a generalized AI model."
                    ),
                ],
            },
            {
                "id": "retention-and-deletion",
                "title": "Retention and Deletion",
                "paragraphs": [
                    (
                        "The data lifecycle for each feature is described in the "
                        "Zero Retention Policy at https://mparanza.com/zero-retention. "
                        "The phrase zero retention has the feature-specific meaning "
                        "stated there. It does not mean that every feature never "
                        "receives, temporarily stores, or processes information."
                    ),
                    (
                        "Some features process content only for a request. Others "
                        "use temporary working storage, periodic or event-triggered "
                        "cleanup, or intentional storage that continues until "
                        "manual or administrative deletion. Link expiry, revocation, "
                        "or archive status may restrict access without deleting the "
                        "underlying content."
                    ),
                    (
                        "Deletion from Mparanza-controlled active storage may not "
                        "immediately remove information from active memory, technical "
                        "logs, delivered messages, infrastructure backups, records "
                        "required for law or security, or systems operated by others. "
                        "Files created by ordinary plugin functions remain under "
                        "your control "
                        "and must be deleted from your environment by you."
                    ),
                    (
                        "Retrieve any content or output you wish to keep before its "
                        "applicable deletion event. Mparanza does not guarantee that "
                        "deleted content can be recovered."
                    ),
                ],
            },
            {
                "id": "professional-review",
                "title": "No Professional Advice",
                "paragraphs": [
                    (
                        "The Service may help draft, extract, classify, reconcile, "
                        "validate, summarize, analyze, or generate content. The "
                        "Service does not provide legal, tax, accounting, audit, "
                        "financial, investment, medical, compliance, or other "
                        "professional advice."
                    ),
                    (
                        "Outputs may be incomplete, inaccurate, outdated, biased, "
                        "or unsuitable for your situation. You are solely "
                        "responsible for reviewing outputs, verifying sources, "
                        "validating calculations, preserving records, and making "
                        "all professional, business, legal, and operational "
                        "decisions."
                    ),
                ],
            },
            {
                "id": "prohibited-use",
                "title": "Prohibited Use",
                "paragraphs": [
                    "You must not use the Service to:",
                ],
                "bullets": [
                    (
                        "violate law, infringe rights, misappropriate data, or "
                        "submit content you do not have the right to process;"
                    ),
                    (
                        "process highly sensitive, regulated, illegal, harmful, "
                        "or confidential information unless you have confirmed "
                        "that the Service is appropriate for that use and you "
                        "have all required authorizations;"
                    ),
                    (
                        "build malware, spam, phishing, fraud, surveillance, "
                        "credential theft, or deceptive systems;"
                    ),
                    (
                        "interfere with, overload, probe, scan, scrape, reverse "
                        "engineer, bypass access controls, or compromise the "
                        "Service or any related system;"
                    ),
                    (
                        "resell, sublicense, rent, benchmark, or commercially "
                        "exploit the Service without Mparanza's written permission;"
                    ),
                    (
                        "use outputs as the sole basis for decisions that could "
                        "affect legal rights, financial outcomes, employment, "
                        "credit, housing, healthcare, safety, or other high-impact "
                        "interests."
                    ),
                ],
            },
            {
                "id": "third-party-services",
                "title": "Third-Party Services",
                "paragraphs": [
                    (
                        "Ordinary plugin functions use your existing ChatGPT plan and "
                        "any connectors or browser services you choose. Mparanza does "
                        "not transmit that content merely because the plugin uses them."
                    ),
                    (
                        "When a Mparanza-hosted service uses an external provider for "
                        "hosting, authentication, communications, model processing, or "
                        "infrastructure, you direct and authorize Mparanza to transmit "
                        "the content described for that hosted service."
                    ),
                    (
                        "External systems are outside Mparanza's direct control. "
                        "Their availability, processing, retention, and deletion "
                        "may differ from Mparanza-controlled systems, and deleting "
                        "content from Mparanza may not delete a copy held elsewhere. "
                        "Mparanza is not responsible for external services, content, "
                        "failures, delays, suspensions, or changes."
                    ),
                ],
            },
            {
                "id": "mparanza-ip",
                "title": "Mparanza Materials",
                "paragraphs": [
                    (
                        "Mparanza and its licensors own the Service, software, "
                        "workflows, templates, interfaces, documentation, designs, "
                        "logos, trademarks, and other materials made available "
                        "through the Service, except for User Content and third-party "
                        "materials. Subject to these Terms, Mparanza grants you a "
                        "limited, revocable, non-exclusive, non-transferable license "
                        "to access and use the Service for your internal lawful "
                        "purposes."
                    ),
                    (
                        "If you provide feedback or suggestions, Mparanza may use "
                        "them without restriction or compensation to you."
                    ),
                ],
            },
            {
                "id": "zero-retention-policy",
                "title": "Zero Retention and Privacy",
                "paragraphs": [
                    (
                        "The Zero Retention Policy at "
                        "https://mparanza.com/zero-retention describes how Mparanza "
                        "handles Customer Content and personal information, the "
                        "difference between ordinary plugin functions and "
                        "Mparanza-hosted services, current retention behavior, and "
                        "available privacy rights."
                    ),
                    (
                        "If these Terms and the Zero Retention Policy describe a "
                        "data lifecycle at different levels of specificity, the "
                        "more specific feature-level description controls, subject "
                        "to applicable law."
                    ),
                ],
            },
            {
                "id": "disclaimers",
                "title": "Disclaimers",
                "paragraphs": [
                    (
                        "To the maximum extent permitted by law, the Service and "
                        "all outputs, materials, downloads, plugins, documentation, "
                        "and third-party integrations are provided as is and as "
                        "available, with all faults and without warranties of any "
                        "kind, whether express, implied, statutory, or otherwise."
                    ),
                    (
                        "Mparanza disclaims all warranties, including warranties "
                        "of title, non-infringement, merchantability, fitness for "
                        "a particular purpose, accuracy, availability, reliability, "
                        "security, uninterrupted operation, error-free operation, "
                        "data preservation, and that outputs will meet your needs "
                        "or comply with law."
                    ),
                ],
            },
            {
                "id": "liability",
                "title": "Limitation of Liability",
                "paragraphs": [
                    (
                        "To the maximum extent permitted by law, Mparanza and its "
                        "owners, affiliates, officers, employees, contractors, "
                        "agents, suppliers, licensors, and service providers will "
                        "not be liable for indirect, incidental, special, "
                        "consequential, exemplary, enhanced, or punitive damages; "
                        "lost profits, revenue, goodwill, business, opportunities, "
                        "or anticipated savings; loss, corruption, exposure, or "
                        "unavailability of data; business interruption; substitute "
                        "services; professional errors; or decisions made from "
                        "outputs, even if advised of the possibility of those "
                        "damages."
                    ),
                    (
                        "To the maximum extent permitted by law, Mparanza's total "
                        "aggregate liability for all claims relating to the Service "
                        "is limited to zero U.S. dollars because the Service is "
                        "currently free. If a court requires a monetary liability "
                        "cap, the cap will be the amount you paid Mparanza for the "
                        "Service in the 12 months before the claim, which is "
                        "currently zero U.S. dollars."
                    ),
                    (
                        "Some jurisdictions do not allow certain disclaimers or "
                        "limitations. In those jurisdictions, the limits in these "
                        "Terms apply to the greatest extent permitted by law."
                    ),
                ],
            },
            {
                "id": "indemnity",
                "title": "Indemnity",
                "paragraphs": [
                    (
                        "To the maximum extent permitted by law, you will defend, "
                        "indemnify, and hold harmless Mparanza and its owners, "
                        "affiliates, officers, employees, contractors, agents, "
                        "suppliers, licensors, and service providers from and "
                        "against claims, losses, liabilities, damages, judgments, "
                        "penalties, fines, costs, and expenses, including "
                        "reasonable attorneys' fees, arising out of or related to "
                        "your User Content, your use or misuse of the Service, "
                        "your violation of these Terms, your violation of law, or "
                        "your violation of another person's rights."
                    ),
                ],
            },
            {
                "id": "termination",
                "title": "Termination",
                "paragraphs": [
                    (
                        "You may stop using the Service at any time. Mparanza may "
                        "suspend or terminate access, delete hosted accounts or "
                        "content, or discontinue the Service at any time, with or "
                        "without notice, to the maximum extent permitted by law. "
                        "You are responsible for exporting content you wish to keep."
                    ),
                    (
                        "Termination does not itself guarantee immediate deletion. "
                        "Hosted content is handled according to the Retention and "
                        "Deletion section and the Zero Retention Policy. Content "
                        "created or stored by ordinary plugin functions remains in "
                        "your chosen workspace, and Mparanza cannot delete it "
                        "remotely."
                    ),
                    (
                        "The User Content license ends when Mparanza no longer holds "
                        "or processes the relevant content, except that it continues "
                        "solely for permitted residual copies and only for the "
                        "purposes and duration described above. Provisions concerning "
                        "ownership, disclaimers, liability limits, indemnity, "
                        "disputes, and general terms survive termination."
                    ),
                ],
            },
            {
                "id": "disputes",
                "title": "Disputes",
                "paragraphs": [
                    (
                        "These Terms are governed by the laws of the United States "
                        "and the laws of the State of New York, without regard to "
                        "conflict-of-law rules. To the maximum extent permitted "
                        "by law, you consent to exclusive jurisdiction and venue "
                        "in the state and federal courts located in New York "
                        "County, New York, except that Mparanza may seek injunctive "
                        "or equitable relief in any court with jurisdiction."
                    ),
                    (
                        "To the maximum extent permitted by law, disputes must be "
                        "resolved only on an individual basis. You and Mparanza "
                        "waive any right to a jury trial and any right to bring "
                        "or participate in a class, collective, consolidated, "
                        "private attorney general, or representative action."
                    ),
                ],
            },
            {
                "id": "changes",
                "title": "Changes",
                "paragraphs": [
                    (
                        "Mparanza may update these Terms at any time. Updated "
                        "Terms are effective when posted unless they say otherwise. "
                        "Your continued use of the Service after an update means "
                        "you accept the updated Terms."
                    ),
                ],
            },
            {
                "id": "general",
                "title": "General",
                "paragraphs": [
                    (
                        "If any provision of these Terms is found unenforceable, "
                        "the remaining provisions will remain in effect, and the "
                        "unenforceable provision will be modified to the minimum "
                        "extent necessary to make it enforceable. Mparanza's "
                        "failure to enforce a provision is not a waiver. You may "
                        "not assign these Terms without Mparanza's consent. "
                        "Mparanza may assign these Terms without restriction."
                    ),
                ],
            },
            {
                "id": "contact",
                "title": "Contact",
                "paragraphs": [
                    f"Legal notices and questions should be sent to {CONTACT_EMAIL}.",
                ],
            },
        ],
    },
    "support": {
        "title": "Customer Support",
        "eyebrow": "Mparanza plugins",
        "effective_date": LEGAL_EFFECTIVE_DATE,
        "contact_email": SUPPORT_EMAIL,
        "summary": (
            "Get help with installing, configuring, and using Mparanza Codex "
            "plugins. Support is handled by Mparanza support."
        ),
        "sections": [
            {
                "id": "request-help",
                "title": "Request Help",
                "paragraphs": [
                    (
                        f"Email {SUPPORT_EMAIL} with the plugin name and version, "
                        "your operating system, the Codex surface you are using, "
                        "the steps that led to the problem, and the exact error "
                        "message when available."
                    ),
                    (
                        "Support covers installation, configuration, plugin tools, "
                        "generated workpapers, and unexpected plugin behavior."
                    ),
                ],
            },
            {
                "id": "local-first",
                "title": "Ordinary Functions Support Boundary",
                "paragraphs": [
                    (
                        "Ordinary plugin functions use your existing ChatGPT plan "
                        "and Codex workspace. Mparanza has no automatic access to "
                        "your files, plugin runs, or outputs and cannot inspect them "
                        "unless you choose to share details or invoke a "
                        "Mparanza-hosted service."
                    ),
                ],
            },
            {
                "id": "protect-data",
                "title": "Protect Client Data",
                "paragraphs": [
                    (
                        "Do not email client documents, passwords, API keys, tax "
                        "identifiers, bank details, or other confidential information. "
                        "Start with a description of the issue and, if useful, a "
                        "redacted error message or minimal reproducible example."
                    ),
                ],
            },
            {
                "id": "professional-use",
                "title": "Professional Use",
                "paragraphs": [
                    (
                        "Vera and other Mparanza plugins support professional work; "
                        "they do not replace the professional's review, judgment, or "
                        "responsibility for client advice and filed work."
                    ),
                ],
            },
        ],
    },
}


def get_legal_page(slug: str) -> dict[str, Any]:
    """Return structured copy for a legal page."""

    return LEGAL_PAGES[slug]
