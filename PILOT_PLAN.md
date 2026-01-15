# Pilot Plan: External Feed Change Detector

## Target persona
- Title: Data platform lead / analytics engineer
- Company: Fintech, e-commerce, adtech, or risk analytics using paid vendor data
- Pain: Vendor feeds change without notice, breaking downstream pipelines and reports

## Pilot hypothesis
If we detect vendor feed changes within 1 run and provide an actionable report, teams will adopt a paid tier to reduce pipeline failures and incident costs.

## Pilot offer (4 weeks)
- Install a sidecar that profiles 1-3 vendor feeds
- Provide automated change reports + Slack alerts
- Deliver a weekly summary of changes and impact
- Pricing anchor: $300-$800 per feed per month after pilot

## Pilot steps
1. Identify 10-15 companies using 3rd-party data feeds.
2. Offer a 2-week proof using a single feed.
3. If value is shown, expand to 3 feeds for weeks 3-4.
4. Convert to paid tier after pilot with a per-feed plan.

## Success criteria
- At least 1 meaningful change detected in the pilot period
- At least 1 incident or costly investigation avoided
- Pilot user confirms the report saved time or prevented a break

## Outreach script (email)
Subject: Quick way to catch vendor feed changes before they break reports

Hi {Name},

I am building a lightweight sidecar that detects silent schema and semantic changes in 3rd-party data feeds. It generates a change report and alerts before downstream systems break.

If you rely on vendor data (pricing, risk, enrichment), I can set up a no-cost 2-week pilot on one feed. You will get a weekly report and real-time alerts for suspicious changes.

Interested in a quick 15-minute call to see if this fits your stack?

Thanks,
{Your Name}

## Outreach script (LinkedIn)
Hi {Name} - I am building a tool that detects vendor feed changes (schema + semantic) before they break pipelines. If you use 3rd-party data, I can run a no-cost 2-week pilot on one feed. Open to a quick chat?

## Call agenda
1. Current vendor feeds and top pain points
2. Recent incidents caused by feed changes
3. Show a sample change report and alert
4. Pilot scope and success criteria

## Pilot deliverables
- 1 change report per run
- Slack or webhook alerts for high-severity changes
- Weekly summary of changes and impact

## Exit criteria
- Confirmed signal that feed change detection prevents or reduces incidents
- Paid conversion or a clear path to paid rollout
