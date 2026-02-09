from django.db import models


class Patient(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id


class Organization(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id


class Provider(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id


class Payer(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id


class Encounter(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    provider = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True, blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id


class Claim(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    provider = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True, blank=True)
    encounter = models.ForeignKey(Encounter, on_delete=models.SET_NULL, null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id


class Observation(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    encounter = models.ForeignKey(Encounter, on_delete=models.SET_NULL, null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id


class Immunization(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    encounter = models.ForeignKey(Encounter, on_delete=models.SET_NULL, null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id


class PayerTransition(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    payer = models.ForeignKey(Payer, on_delete=models.SET_NULL, null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id


class ClaimTransaction(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True)
    provider = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True, blank=True)
    encounter = models.ForeignKey(Encounter, on_delete=models.SET_NULL, null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.id

