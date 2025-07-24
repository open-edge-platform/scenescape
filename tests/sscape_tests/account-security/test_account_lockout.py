# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.test.client import RequestFactory
from manager.settings import AXES_FAILURE_LIMIT

class AccountLockoutTestCase(TestCase):

  def setUp(self):
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')

  def test_account_is_locked(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    attempt = 0
    while(attempt < AXES_FAILURE_LIMIT):
      response = self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'wrong'})
      attempt += 1

    self.assertEqual(response.status_code, 302)
