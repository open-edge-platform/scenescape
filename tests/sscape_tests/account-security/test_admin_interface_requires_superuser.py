# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.test.client import RequestFactory

class AccountLockoutTestCase(TestCase):

  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_user('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})

  def test_admin_interface_requires_superuser(self):
    response = self.client.get('admin/')
    self.assertEqual(response.status_code, 404)
