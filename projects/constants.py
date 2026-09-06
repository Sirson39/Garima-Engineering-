PRIORITY_CHOICES = [
    ("Urgent", "Urgent"),
    ("High", "High"),
    ("Normal", "Normal"),
    ("Low", "Low"),
]

PROJECT_STATUS_CHOICES = [
    ("New", "New"),
    ("Documents Pending", "Documents Pending"),
    ("Documents Verification", "Documents Verification"),
    ("Ready for Online Entry", "Ready for Online Entry"),
    ("Plan Preparation", "Plan Preparation"),
    ("Waiting for Client Approval", "Waiting for Client Approval"),
    ("Waiting for Ward", "Waiting for Ward"),
    ("Structural Work", "Structural Work"),
    ("Online Processing", "Online Processing"),
    ("Ready for Municipality", "Ready for Municipality"),
    ("At Municipality", "At Municipality"),
    ("Correction Required", "Correction Required"),
    ("Approved", "Approved"),
    ("Delivered", "Delivered"),
    ("Payment Pending", "Payment Pending"),
    ("Completed", "Completed"),
    ("Archived", "Archived"),
    ("Cancelled", "Cancelled"),
    ("On Hold", "On Hold"),
]

STAGE_STATUS_CHOICES = PROJECT_STATUS_CHOICES

WAIT_TYPE_CHOICES = [
    ("internal", "Internal"),
    ("client", "Waiting for client"),
    ("ward", "Waiting for ward"),
    ("municipality", "Waiting for municipality"),
    ("employee", "Waiting for employee"),
    ("payment", "Waiting for payment"),
]

TASK_STATUS_CHOICES = [
    ("New", "New"),
    ("Assigned", "Assigned"),
    ("In Progress", "In Progress"),
    ("Waiting", "Waiting"),
    ("Correction Required", "Correction Required"),
    ("Completed", "Completed"),
    ("Cancelled", "Cancelled"),
]

TASK_PRIORITY_CHOICES = PRIORITY_CHOICES

FILE_LOCATION_CHOICES = [
    ("Reception", "Reception"),
    ("Planning engineer", "Planning engineer"),
    ("Structural engineer", "Structural engineer"),
    ("Online processing officer", "Online processing officer"),
    ("Municipality file handler", "Municipality file handler"),
    ("Client", "Client"),
    ("Ward office", "Ward office"),
    ("Municipality", "Municipality"),
    ("Management", "Management"),
    ("Archive", "Archive"),
]

DOCUMENT_APPROVAL_CHOICES = [
    ("Pending", "Pending"),
    ("Checked", "Checked"),
    ("Approved", "Approved"),
    ("Rejected", "Rejected"),
]

DOCUMENT_CONFIDENTIALITY_CHOICES = [
    ("Public", "Public"),
    ("Internal", "Internal"),
    ("Confidential", "Confidential"),
    ("Restricted", "Restricted"),
]

PAYMENT_METHOD_CHOICES = [
    ("Cash", "Cash"),
    ("Bank Transfer", "Bank Transfer"),
    ("Cheque", "Cheque"),
    ("Digital Payment", "Digital Payment"),
]

VISIT_STATUS_CHOICES = [
    ("Scheduled", "Scheduled"),
    ("Confirmed", "Confirmed"),
    ("Completed", "Completed"),
    ("Cancelled", "Cancelled"),
    ("Follow-up Required", "Follow-up Required"),
]

ONLINE_STATUS_CHOICES = [
    ("Not Started", "Not Started"),
    ("Submitted", "Submitted"),
    ("Under Review", "Under Review"),
    ("Correction Requested", "Correction Requested"),
    ("Approved", "Approved"),
    ("Rejected", "Rejected"),
]

MUNICIPALITY_ACTIVITY_CHOICES = [
    ("Comment", "Comment"),
    ("Correction Request", "Correction Request"),
    ("Approval", "Approval"),
    ("Signature", "Signature"),
]

SUBMISSION_TYPE_CHOICES = [
    ("Initial", "Initial"),
    ("Ward Upload", "Ward Upload"),
    ("Structural Upload", "Structural Upload"),
    ("Resubmission", "Resubmission"),
    ("Final Upload", "Final Upload"),
]

