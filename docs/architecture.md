# Garima Engineering Consultancy Management System

## Database Architecture

The application uses PostgreSQL in production and is structured around a small set of core domain groups:

| Domain | Tables | Purpose |
| --- | --- | --- |
| Identity | `accounts_user`, `auth_group`, `auth_permission` | Individual employee accounts and configurable role groups |
| Branding and audit | `core_organizationprofile`, `core_auditlog`, `core_notification`, `core_loginattempt` | Company settings, audit trail, notifications, login throttling |
| Workflow setup | `workflows_servicetype`, `workflows_numberingscheme`, `workflows_documentcategory`, `workflows_workflowstagetemplate`, `workflows_documenttemplate` | Service definitions, numbering rules, stages, and document checklists |
| Clients and projects | `projects_client`, `projects_project` | Client records and the main project register |
| Checklist and docs | `projects_documentchecklistitem`, `projects_projectdocument` | Mandatory/optional document tracking and revisioned file storage |
| Workflow history | `projects_projectstagehistory`, `projects_stageattachment` | Stage movement history and stage attachments |
| Work management | `projects_task`, `projects_taskattachment` | Tasks automatically created from workflow transitions |
| Site operations | `projects_sitevisit`, `projects_sitevisitattachment` | Site-visit planning and evidence capture |
| Government tracking | `projects_governmentrecord` | Online submission tracking and receipts |
| Municipality tracking | `projects_municipalityactivity` | Comments, corrections, approvals, and signature handling |
| File register | `projects_physicalfiletransfer` | Physical file handover history and current file holder |
| Finance | `projects_payment` | Simple project payment tracking |
| Notes | `projects_projectcomment` | Internal and client-visible comments |

## User Roles And Permissions

Default role groups are seeded as Django `Group` records and can be edited in the admin:

| Role | Intended Access |
| --- | --- |
| System Administrator | Full access to everything |
| Director/Management | Full operational oversight and approval rights |
| Reception/Document Officer | Client intake, checklist updates, uploads, handovers |
| Project Manager | Workflow control, task assignment, exception approval |
| Planning Engineer | Plan preparation and revisions |
| Structural Engineer | Structural design and technical review |
| Site Engineer | Site visits and survey notes |
| Online Processing Officer | Online portal preparation and uploads |
| Municipality File Handler | Municipality tracking and file transfers |
| Accounts Officer | Payment recording and balance tracking |
| Read-only/Auditor | Read-only access |

## Page And Screen List

| Screen | Route | Notes |
| --- | --- | --- |
| Dashboard | `/` | Management and employee stats |
| New Project | `/projects/new/` | Create a project and generate a project number |
| All Projects | `/projects/` | Searchable and filterable project register |
| My Tasks | `/tasks/` | Employee task queue |
| Clients | `/clients/` | Client register |
| Documents | `/documents/` | Revisioned document register |
| Physical File Register | `/file-register/` | File handover history |
| Site Visits | `/site-visits/` | Site visit log |
| Government Online Records | `/government-records/` | Submission tracking |
| Municipality Tracking | `/municipality-tracking/` | Municipality notes and approvals |
| Payments | `/payments/` | Simple payment tracking |
| Reports | `/reports/` | Overview summary |
| Users and Roles | `/users/` | Staff directory and group overview |
| System Settings | `/settings/` | Branding and office settings |
| Workflow Catalog | `/workflows/` | Workflow and numbering overview |

## Naya Naksa Workflow Model

The seeded workflow follows 32 stages, starting with registration and ending with archive closure. The implementation stores the stages as configurable `WorkflowStageTemplate` rows. Each project keeps:

* Current stage template
* Current stage history row
* Assigned employee
* Due date
* Completion date
* Delay notes and correction reason

Mandatory documents are checked before stage advancement. Management can approve an exception, which is audited.

## Abhilekhikaran Workflow Model

The seeded workflow follows 28 stages and adds site visits, existing-building drawings, and municipality follow-up. The same workflow engine is reused:

* Stage templates define the ordered process
* Document templates define the checklist
* Stage history records every move
* Tasks are created automatically for the next assignee

## Light Theme UI Design System

* White and light-grey surfaces
* Blue/teal primary colour palette
* Small accent colour for important actions
* Clear tables, badges, and forms
* Left sidebar for desktop, offcanvas sidebar on mobile
* Bootstrap 5 layout with lightweight custom CSS
* English/Nepali Unicode-friendly typography and spacing

## Project Structure

```text
config/      Django settings and URL routing
accounts/    Custom user model, login, roles overview
core/        Branding, audit logs, notifications, dashboard, settings
workflows/   Service types, numbering, stages, and document templates
projects/    Clients, projects, documents, tasks, file history, site visits, finance
templates/   Shared Bootstrap templates
static/      Custom CSS and assets
docs/        Architecture and handoff documentation
```

## Implementation Plan

1. Authentication and staff accounts
2. Clients and project register
3. Workflow templates and numbering schemes
4. Document checklist generation and revisioned uploads
5. Automatic task creation on stage movement
6. Physical file register and QR code labels
7. Site visits, government submissions, municipality tracking, and payments
8. Reporting, audit history, and security hardening

## Backup And Restore

### PostgreSQL backup

```bash
pg_dump -U <db_user> -h <db_host> -Fc <db_name> > backups/garima.backup
```

### PostgreSQL restore

```bash
pg_restore -U <db_user> -h <db_host> -d <db_name> --clean --if-exists backups/garima.backup
```

### Media backup

Back up the `media/` directory or the configured object storage bucket alongside the database.

