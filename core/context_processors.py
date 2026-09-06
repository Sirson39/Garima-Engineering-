from core.models import OrganizationProfile


def organization(request):
    return {"organization": OrganizationProfile.load()}

