#!/usr/bin/env python3
"""
BFCMS Super Admin Testing Suite
Tests Super Admin authentication and permissions as specified in the review request
"""

import requests
import sys
import json
from datetime import datetime

class SuperAdminTester:
    def __init__(self, base_url="https://choir-admin.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.super_admin_token = None
        self.member_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.created_member_id = None
        self.created_user_id = None

    def log_result(self, test_name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name} - {details}")
        
        self.test_results.append({
            'test': test_name,
            'success': success,
            'details': details
        })

    def make_request(self, method, endpoint, data=None, token=None, expected_status=200):
        """Make HTTP request with proper headers"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            success = response.status_code == expected_status
            try:
                response_data = response.json() if response.content else {}
            except:
                response_data = {'raw_response': response.text}
            
            return success, response_data, response.status_code

        except Exception as e:
            return False, {'error': str(e)}, 0

    def test_super_admin_authentication(self):
        """Test 1: Super Admin Authentication"""
        print("\n🔐 Test 1: Super Admin Authentication")
        
        login_data = {
            "email": "superadmin@bfcms.com",
            "password": "Admin@123"
        }
        
        success, response, status = self.make_request('POST', 'auth/login', login_data, expected_status=200)
        
        if success and 'token' in response and 'user' in response:
            user = response['user']
            if user.get('role') == 'super_admin':
                self.super_admin_token = response['token']
                self.log_result("Super Admin Login", True, f"Token received, role: {user.get('role')}")
                return True
            else:
                self.log_result("Super Admin Login", False, f"Wrong role: {user.get('role')}")
                return False
        else:
            self.log_result("Super Admin Login", False, f"Status: {status}, Response: {response}")
            return False

    def test_super_admin_add_member(self):
        """Test 2: Super Admin Can Add Members"""
        print("\n👥 Test 2: Super Admin Can Add Members")
        
        if not self.super_admin_token:
            self.log_result("Add Member (No Token)", False, "Super Admin token not available")
            return False
        
        # Create member with specific test data as requested
        member_data = {
            "full_name": "Test Member",
            "id_number": "12345678",
            "phone": "+254700000001",
            "email": "testmember@test.com",
            "department": "soprano"
        }
        
        success, response, status = self.make_request(
            'POST', 'members', member_data, 
            token=self.super_admin_token, 
            expected_status=200
        )
        
        if success and 'membership_number' in response:
            # Verify membership number format (BFC-YYYY-XXXX)
            membership_number = response['membership_number']
            year = datetime.now().year
            expected_prefix = f"BFC-{year}-"
            
            if membership_number.startswith(expected_prefix):
                self.created_member_id = response['id']
                self.log_result("Add Member", True, f"Member created with membership_number: {membership_number}")
                return True
            else:
                self.log_result("Add Member", False, f"Invalid membership number format: {membership_number}")
                return False
        else:
            self.log_result("Add Member", False, f"Status: {status}, Response: {response}")
            return False

    def test_super_admin_full_access(self):
        """Test 3: Super Admin Full Access Verification"""
        print("\n🔑 Test 3: Super Admin Full Access Verification")
        
        if not self.super_admin_token:
            self.log_result("Full Access Test (No Token)", False, "Super Admin token not available")
            return False
        
        # Test all endpoints that super admin should have access to
        endpoints_to_test = [
            ('members', 'GET'),
            ('disciplinary', 'GET'),
            ('inventory', 'GET'),
            ('notices', 'GET'),
            ('documents', 'GET'),
            ('users', 'GET'),  # Only super_admin should have access
            ('dashboard/stats', 'GET')
        ]
        
        all_passed = True
        for endpoint, method in endpoints_to_test:
            success, response, status = self.make_request(
                method, endpoint, 
                token=self.super_admin_token, 
                expected_status=200
            )
            
            if success:
                self.log_result(f"Access {endpoint}", True)
            else:
                self.log_result(f"Access {endpoint}", False, f"Status: {status}")
                all_passed = False
        
        return all_passed

    def test_regular_member_restrictions(self):
        """Test 4: Regular Member Role Restriction"""
        print("\n🚫 Test 4: Regular Member Role Restriction")
        
        # First create a regular member user
        timestamp = datetime.now().strftime('%H%M%S')
        register_data = {
            "email": f"testuser_{timestamp}@test.com",
            "password": "testpass123",
            "full_name": "Test Regular User",
            "role": "member"
        }
        
        success, response, status = self.make_request('POST', 'auth/register', register_data, expected_status=200)
        
        if success and 'token' in response:
            self.member_token = response['token']
            self.created_user_id = response['user']['id']
            self.log_result("Create Regular Member User", True)
        else:
            self.log_result("Create Regular Member User", False, f"Status: {status}, Response: {response}")
            return False
        
        # Test that regular member cannot add members (should return 403)
        member_data = {
            "full_name": "Unauthorized Member",
            "id_number": "87654321",
            "phone": "+254700000002",
            "email": "unauthorized@test.com",
            "department": "alto"
        }
        
        success, response, status = self.make_request(
            'POST', 'members', member_data,
            token=self.member_token,
            expected_status=403
        )
        
        if success:  # Success means we got 403 as expected
            self.log_result("Member Cannot Add Members", True, "403 Forbidden as expected")
        else:
            self.log_result("Member Cannot Add Members", False, f"Expected 403, got {status}")
        
        # Test that regular member cannot access users endpoint (should return 403)
        success, response, status = self.make_request(
            'GET', 'users',
            token=self.member_token,
            expected_status=403
        )
        
        if success:  # Success means we got 403 as expected
            self.log_result("Member Cannot Access Users", True, "403 Forbidden as expected")
            return True
        else:
            self.log_result("Member Cannot Access Users", False, f"Expected 403, got {status}")
            return False

    def cleanup_test_data(self):
        """Clean up created test data"""
        print("\n🧹 Cleaning up test data...")
        
        # Delete created member if exists
        if self.created_member_id and self.super_admin_token:
            success, _, _ = self.make_request(
                'DELETE', f'members/{self.created_member_id}',
                token=self.super_admin_token,
                expected_status=200
            )
            if success:
                print(f"✅ Deleted test member {self.created_member_id}")
            else:
                print(f"⚠️ Could not delete test member {self.created_member_id}")

    def run_all_tests(self):
        """Run all test suites"""
        print("🚀 Starting BFCMS Super Admin Tests...")
        print(f"📍 Testing against: {self.base_url}")
        
        # Run tests in sequence
        test1_passed = self.test_super_admin_authentication()
        test2_passed = self.test_super_admin_add_member() if test1_passed else False
        test3_passed = self.test_super_admin_full_access() if test1_passed else False
        test4_passed = self.test_regular_member_restrictions()
        
        # Cleanup
        self.cleanup_test_data()
        
        # Print summary
        print(f"\n📊 Test Summary:")
        print(f"Tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {self.tests_run - self.tests_passed}")
        print(f"Success rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        
        # Print detailed results
        print(f"\n📋 Detailed Results:")
        for result in self.test_results:
            status = "✅" if result['success'] else "❌"
            details = f" - {result['details']}" if result['details'] else ""
            print(f"{status} {result['test']}{details}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = SuperAdminTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())