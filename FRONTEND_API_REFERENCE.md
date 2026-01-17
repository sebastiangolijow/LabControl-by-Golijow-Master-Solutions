# Frontend API Reference - LabControl

**Version:** 1.0
**Last Updated:** 2025-12-26
**Backend API Version:** v1
**Target:** Vue 3 + Vite Frontend Development

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Authentication](#authentication)
3. [API Endpoints](#api-endpoints)
4. [Request/Response Patterns](#requestresponse-patterns)
5. [Error Handling](#error-handling)
6. [File Uploads](#file-uploads)
7. [Pagination](#pagination)
8. [Vue 3 Integration Examples](#vue-3-integration-examples)
9. [Environment Configuration](#environment-configuration)

---

## Getting Started

### Base URL

```typescript
// Development
const API_BASE_URL = 'http://localhost:8000/api/v1'

// Production
const API_BASE_URL = 'https://api.labcontrol.com/api/v1'
```

### CORS Configuration

The backend is configured to accept requests from:
- `http://localhost:3000` (Vite default)
- `http://localhost:8080` (Vue CLI default)
- Production frontend domain

**Credentials:** Cookies are allowed (`credentials: 'include'`)

---

## Authentication

### Authentication Methods

LabControl supports two authentication methods:
1. **JWT Tokens** (Recommended for SPA)
2. **Session Authentication** (for admin panel)

### JWT Token Flow

#### 1. User Registration (Patient)

**Endpoint:** `POST /api/v1/users/register/`

**Request:**
```typescript
interface RegistrationRequest {
  email: string;
  password: string;
  password_confirm: string;
  first_name: string;
  last_name: string;
  phone_number?: string;
  lab_client_id: number;
}
```

**Example:**
```javascript
const response = await fetch(`${API_BASE_URL}/users/register/`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    email: 'patient@example.com',
    password: 'SecurePass123!',
    password_confirm: 'SecurePass123!',
    first_name: 'John',
    last_name: 'Doe',
    phone_number: '+1234567890',
    lab_client_id: 1
  })
});

const data = await response.json();
```

**Response (201 Created):**
```json
{
  "user": {
    "id": 123,
    "email": "patient@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "phone_number": "+1234567890",
    "role": "patient",
    "lab_client_id": 1,
    "is_verified": false,
    "date_joined": "2025-12-26T10:30:00Z"
  },
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "message": "Registration successful. Please verify your email."
}
```

#### 2. User Login

**Endpoint:** `POST /api/v1/auth/login/`

**Request:**
```typescript
interface LoginRequest {
  email: string;
  password: string;
}
```

**Example:**
```javascript
const response = await fetch(`${API_BASE_URL}/auth/login/`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    email: 'patient@example.com',
    password: 'SecurePass123!'
  })
});

const data = await response.json();
```

**Response (200 OK):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": 123,
    "email": "patient@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "role": "patient",
    "lab_client_id": 1
  }
}
```

**Error Response (400 Bad Request):**
```json
{
  "non_field_errors": [
    "Unable to log in with provided credentials."
  ]
}
```

**Rate Limiting (429 Too Many Requests):**
```json
{
  "detail": "Request was throttled. Expected available in 900 seconds."
}
```

#### 3. Token Refresh

**Endpoint:** `POST /api/v1/auth/token/refresh/`

**Request:**
```javascript
const response = await fetch(`${API_BASE_URL}/auth/token/refresh/`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    refresh: refreshToken
  })
});
```

**Response:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

#### 4. Logout

**Endpoint:** `POST /api/v1/auth/logout/`

**Request:**
```javascript
await fetch(`${API_BASE_URL}/auth/logout/`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});
```

### Using JWT Tokens

**All authenticated requests must include the Authorization header:**

```javascript
headers: {
  'Authorization': `Bearer ${accessToken}`,
  'Content-Type': 'application/json'
}
```

---

## API Endpoints

### User Roles

- **patient**: Can view their own data only
- **lab_staff**: Can upload results
- **lab_manager**: Can manage patients and results (within their lab)
- **admin**: Full access to all labs
- **doctor**: Can view patient results (if assigned)

### Public Endpoints (No Auth Required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/users/register/` | Patient registration |
| POST | `/api/v1/auth/login/` | User login |
| POST | `/api/v1/auth/password/reset/` | Request password reset |

### Patient Endpoints (Requires patient auth)

| Method | Endpoint | Description | Response |
|--------|----------|-------------|----------|
| GET | `/api/v1/studies/` | List patient's studies | Paginated list |
| GET | `/api/v1/studies/{id}/` | View study details | Study object |
| GET | `/api/v1/studies/{id}/download_result/` | Download PDF | File download |
| GET | `/api/v1/studies/types/` | List available study types | Study types |
| GET | `/api/v1/notifications/` | List notifications | Paginated list |
| POST | `/api/v1/notifications/{id}/mark_as_read/` | Mark as read | Success message |
| POST | `/api/v1/notifications/mark_all_as_read/` | Mark all as read | Success message |
| GET | `/api/v1/notifications/unread_count/` | Get unread count | `{unread_count: number}` |

### Admin/Lab Manager Endpoints

| Method | Endpoint | Description | Permission |
|--------|----------|-------------|------------|
| GET | `/api/v1/users/search-patients/` | Search patients | Admin, Lab Manager |
| POST | `/api/v1/studies/{id}/upload_result/` | Upload results | Lab Staff, Admin, Manager |
| DELETE | `/api/v1/studies/{id}/delete-result/` | Delete results | Admin, Manager only |
| GET | `/api/v1/studies/with-results/` | List studies with results | Admin, Manager |
| GET | `/api/v1/analytics/dashboard/` | Analytics dashboard | Admin, Manager |

---

## Request/Response Patterns

### Study List (GET /api/v1/studies/)

**Request:**
```javascript
const response = await fetch(`${API_BASE_URL}/studies/`, {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});
```

**Response:**
```json
{
  "count": 25,
  "next": "http://localhost:8000/api/v1/studies/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "uuid": "550e8400-e29b-41d4-a716-446655440000",
      "order_number": "LAB-2025-00123",
      "patient": 5,
      "patient_detail": {
        "id": 5,
        "email": "patient@example.com",
        "first_name": "John",
        "last_name": "Doe"
      },
      "study_type": 2,
      "study_type_detail": {
        "id": 2,
        "name": "Complete Blood Count",
        "code": "CBC",
        "category": "Hematology",
        "description": "Complete blood count test",
        "price": "50.00"
      },
      "status": "completed",
      "created_at": "2025-12-20T10:00:00Z",
      "updated_at": "2025-12-21T14:30:00Z",
      "completed_at": "2025-12-21T14:30:00Z",
      "results_file": "https://storage.googleapis.com/bucket/results/LAB-2025-00123.pdf",
      "results": "All values within normal range"
    }
  ]
}
```

### Study Detail (GET /api/v1/studies/{id}/)

**Response:**
```json
{
  "id": 1,
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "order_number": "LAB-2025-00123",
  "patient": 5,
  "patient_detail": {
    "id": 5,
    "email": "patient@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "phone_number": "+1234567890"
  },
  "study_type": 2,
  "study_type_detail": {
    "id": 2,
    "name": "Complete Blood Count",
    "code": "CBC",
    "category": "Hematology",
    "description": "Complete blood count test",
    "price": "50.00",
    "estimated_duration_minutes": 30,
    "requires_fasting": false,
    "sample_type": "Blood"
  },
  "status": "completed",
  "priority": "normal",
  "sample_collected_at": "2025-12-20T11:00:00Z",
  "created_at": "2025-12-20T10:00:00Z",
  "updated_at": "2025-12-21T14:30:00Z",
  "completed_at": "2025-12-21T14:30:00Z",
  "results_file": "https://storage.googleapis.com/bucket/results/LAB-2025-00123.pdf",
  "results": "All values within normal range",
  "notes": "Patient was fasting for 8 hours"
}
```

### Notifications (GET /api/v1/notifications/)

**Response:**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 12,
      "title": "Your Blood Test Results Are Ready",
      "message": "Your Complete Blood Count results are now available for download.",
      "notification_type": "result_ready",
      "channel": "in_app",
      "status": "sent",
      "created_at": "2025-12-21T14:30:00Z",
      "read_at": null,
      "related_study_id": 1,
      "metadata": {
        "study_type": "Complete Blood Count",
        "order_number": "LAB-2025-00123"
      }
    }
  ]
}
```

### Patient Search (GET /api/v1/users/search-patients/)

**Query Parameters:**
- `search`: Search by email, first_name, last_name, phone
- `email`: Filter by exact email
- `ordering`: Sort (e.g., `-date_joined`, `email`)

**Request:**
```javascript
const response = await fetch(
  `${API_BASE_URL}/users/search-patients/?search=john&ordering=last_name`,
  {
    headers: {
      'Authorization': `Bearer ${adminToken}`
    }
  }
);
```

**Response:**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 5,
      "email": "john.doe@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "phone_number": "+1234567890",
      "role": "patient",
      "lab_client_id": 1,
      "date_joined": "2025-12-01T10:00:00Z"
    }
  ]
}
```

---

## Error Handling

### Standard Error Response Format

```typescript
interface ErrorResponse {
  detail?: string;              // Single error message
  non_field_errors?: string[];  // General errors
  [field: string]: string[];    // Field-specific errors
}
```

### Common HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | OK | Successful GET/POST request |
| 201 | Created | Resource created (registration, upload) |
| 204 | No Content | Successful DELETE request |
| 400 | Bad Request | Validation errors, malformed data |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist or access denied |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Internal server error |

### Error Examples

**Validation Error (400):**
```json
{
  "email": ["This field is required."],
  "password": ["This password is too short."],
  "phone_number": ["Enter a valid phone number."]
}
```

**Authentication Error (401):**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**Permission Error (403):**
```json
{
  "detail": "You do not have permission to perform this action."
}
```

**Not Found (404):**
```json
{
  "detail": "Not found."
}
```

**Rate Limit (429):**
```json
{
  "detail": "Request was throttled. Expected available in 900 seconds."
}
```

---

## File Uploads

### Upload Result PDF

**Endpoint:** `POST /api/v1/studies/{id}/upload_result/`

**Content-Type:** `multipart/form-data`

**Allowed File Types:**
- PDF (`.pdf`)
- JPEG (`.jpg`, `.jpeg`)
- PNG (`.png`)

**Max File Size:** 10 MB

**Request (JavaScript with FormData):**
```javascript
const formData = new FormData();
formData.append('results_file', file); // File object from <input type="file">
formData.append('results', 'All values within normal range'); // Optional text

const response = await fetch(`${API_BASE_URL}/studies/${studyId}/upload_result/`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
    // Do NOT set Content-Type - browser sets it automatically with boundary
  },
  body: formData
});
```

**Response (200 OK):**
```json
{
  "message": "Results uploaded successfully.",
  "study": {
    "id": 1,
    "order_number": "LAB-2025-00123",
    "status": "completed",
    "results_file": "https://storage.googleapis.com/bucket/results/LAB-2025-00123.pdf"
  }
}
```

**Error Response (400 Bad Request):**
```json
{
  "results_file": [
    "File type not supported. Only PDF, JPEG, and PNG files are allowed."
  ]
}
```

### Download Result PDF

**Endpoint:** `GET /api/v1/studies/{id}/download_result/`

**Response:** Binary file with headers:
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="results_LAB-2025-00123.pdf"
```

**JavaScript Example:**
```javascript
const response = await fetch(`${API_BASE_URL}/studies/${studyId}/download_result/`, {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});

const blob = await response.blob();
const url = window.URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = `results_${orderNumber}.pdf`;
a.click();
window.URL.revokeObjectURL(url);
```

---

## Pagination

### Default Pagination

All list endpoints return paginated results:

**Page Size:** 20 items per page (default)

**Query Parameters:**
- `page`: Page number (default: 1)
- `page_size`: Items per page (max: 100)

**Example:**
```javascript
const response = await fetch(`${API_BASE_URL}/studies/?page=2&page_size=10`, {
  headers: { 'Authorization': `Bearer ${accessToken}` }
});
```

**Response Structure:**
```json
{
  "count": 45,           // Total number of items
  "next": "http://...?page=3",  // URL to next page (or null)
  "previous": "http://...?page=1",  // URL to previous page (or null)
  "results": [...]       // Array of items for current page
}
```

### Filtering & Ordering

Most list endpoints support:
- `search`: Full-text search
- `ordering`: Sort by field (prefix with `-` for descending)
- Specific field filters

**Example:**
```javascript
// Search studies by order number
GET /api/v1/studies/?search=LAB-2025

// Filter by status
GET /api/v1/studies/?status=completed

// Order by date (newest first)
GET /api/v1/studies/?ordering=-created_at

// Combine filters
GET /api/v1/studies/?status=completed&ordering=-completed_at&page=1
```

---

## Vue 3 Integration Examples

### 1. API Client Setup (Axios)

**`src/api/client.ts`**
```typescript
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

// Create axios instance
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

// Request interceptor to add auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If 401 and not already retried, try to refresh token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        const response = await axios.post(
          `${API_BASE_URL}/auth/token/refresh/`,
          { refresh: refreshToken }
        );

        const { access } = response.data;
        localStorage.setItem('access_token', access);

        // Retry original request with new token
        originalRequest.headers.Authorization = `Bearer ${access}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed, logout user
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
```

### 2. Auth Service

**`src/api/auth.ts`**
```typescript
import apiClient from './client';

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegistrationData {
  email: string;
  password: string;
  password_confirm: string;
  first_name: string;
  last_name: string;
  phone_number?: string;
  lab_client_id: number;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  user: User;
}

export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  role: 'patient' | 'lab_staff' | 'lab_manager' | 'admin' | 'doctor';
  lab_client_id: number;
}

export const authApi = {
  async login(credentials: LoginCredentials): Promise<AuthResponse> {
    const response = await apiClient.post('/auth/login/', credentials);
    return response.data;
  },

  async register(data: RegistrationData): Promise<AuthResponse> {
    const response = await apiClient.post('/users/register/', data);
    return response.data;
  },

  async logout(): Promise<void> {
    await apiClient.post('/auth/logout/');
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  },

  async getCurrentUser(): Promise<User> {
    const response = await apiClient.get('/users/me/');
    return response.data;
  },
};
```

### 3. Studies Service

**`src/api/studies.ts`**
```typescript
import apiClient from './client';

export interface Study {
  id: number;
  uuid: string;
  order_number: string;
  patient: number;
  patient_detail: {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
  };
  study_type_detail: {
    id: number;
    name: string;
    code: string;
    category: string;
  };
  status: 'pending' | 'sample_collected' | 'in_progress' | 'completed' | 'cancelled';
  created_at: string;
  completed_at: string | null;
  results_file: string | null;
  results: string | null;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const studiesApi = {
  async getStudies(page = 1): Promise<PaginatedResponse<Study>> {
    const response = await apiClient.get('/studies/', {
      params: { page }
    });
    return response.data;
  },

  async getStudy(id: number): Promise<Study> {
    const response = await apiClient.get(`/studies/${id}/`);
    return response.data;
  },

  async downloadResult(id: number): Promise<Blob> {
    const response = await apiClient.get(`/studies/${id}/download_result/`, {
      responseType: 'blob'
    });
    return response.data;
  },

  async uploadResult(id: number, file: File, notes?: string): Promise<any> {
    const formData = new FormData();
    formData.append('results_file', file);
    if (notes) {
      formData.append('results', notes);
    }

    const response = await apiClient.post(`/studies/${id}/upload_result/`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      }
    });
    return response.data;
  },
};
```

### 4. Vue Composable (Composition API)

**`src/composables/useStudies.ts`**
```typescript
import { ref, computed } from 'vue';
import { studiesApi, type Study } from '@/api/studies';

export function useStudies() {
  const studies = ref<Study[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const currentPage = ref(1);
  const totalCount = ref(0);

  const hasNextPage = computed(() => {
    return currentPage.value * 20 < totalCount.value;
  });

  const hasPrevPage = computed(() => {
    return currentPage.value > 1;
  });

  async function fetchStudies(page = 1) {
    loading.value = true;
    error.value = null;

    try {
      const response = await studiesApi.getStudies(page);
      studies.value = response.results;
      totalCount.value = response.count;
      currentPage.value = page;
    } catch (e: any) {
      error.value = e.response?.data?.detail || 'Failed to fetch studies';
      console.error('Error fetching studies:', e);
    } finally {
      loading.value = false;
    }
  }

  async function downloadResult(study: Study) {
    try {
      const blob = await studiesApi.downloadResult(study.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `results_${study.order_number}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      error.value = e.response?.data?.detail || 'Failed to download result';
      console.error('Error downloading result:', e);
    }
  }

  return {
    studies,
    loading,
    error,
    currentPage,
    totalCount,
    hasNextPage,
    hasPrevPage,
    fetchStudies,
    downloadResult,
  };
}
```

### 5. Vue Component Example

**`src/components/StudiesList.vue`**
```vue
<script setup lang="ts">
import { onMounted } from 'vue';
import { useStudies } from '@/composables/useStudies';

const {
  studies,
  loading,
  error,
  currentPage,
  hasNextPage,
  hasPrevPage,
  fetchStudies,
  downloadResult
} = useStudies();

onMounted(() => {
  fetchStudies();
});

function nextPage() {
  fetchStudies(currentPage.value + 1);
}

function prevPage() {
  fetchStudies(currentPage.value - 1);
}
</script>

<template>
  <div class="studies-list">
    <h2>My Lab Results</h2>

    <div v-if="loading" class="loading">
      Loading studies...
    </div>

    <div v-else-if="error" class="error">
      {{ error }}
    </div>

    <div v-else-if="studies.length === 0" class="empty">
      No studies found.
    </div>

    <div v-else class="studies">
      <div
        v-for="study in studies"
        :key="study.id"
        class="study-card"
      >
        <div class="study-header">
          <h3>{{ study.study_type_detail.name }}</h3>
          <span :class="`status status-${study.status}`">
            {{ study.status }}
          </span>
        </div>

        <div class="study-info">
          <p><strong>Order:</strong> {{ study.order_number }}</p>
          <p><strong>Date:</strong> {{ new Date(study.created_at).toLocaleDateString() }}</p>
          <p v-if="study.completed_at">
            <strong>Completed:</strong> {{ new Date(study.completed_at).toLocaleDateString() }}
          </p>
        </div>

        <div v-if="study.results_file" class="study-actions">
          <button @click="downloadResult(study)" class="btn-download">
            Download Results
          </button>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div class="pagination">
      <button
        @click="prevPage"
        :disabled="!hasPrevPage"
        class="btn-page"
      >
        Previous
      </button>
      <span>Page {{ currentPage }}</span>
      <button
        @click="nextPage"
        :disabled="!hasNextPage"
        class="btn-page"
      >
        Next
      </button>
    </div>
  </div>
</template>

<style scoped>
.studies-list {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem;
}

.study-card {
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1rem;
}

.status {
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-size: 0.875rem;
  font-weight: 500;
}

.status-completed {
  background: #d4edda;
  color: #155724;
}

.status-in_progress {
  background: #fff3cd;
  color: #856404;
}

.btn-download {
  background: #007bff;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
}

.btn-download:hover {
  background: #0056b3;
}
</style>
```

---

## Environment Configuration

### Vite Environment Variables

Create `.env.development` and `.env.production` files:

**`.env.development`**
```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_APP_NAME=LabControl
```

**`.env.production`**
```bash
VITE_API_BASE_URL=https://api.labcontrol.com/api/v1
VITE_APP_NAME=LabControl
```

### TypeScript Environment Types

**`src/vite-env.d.ts`**
```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_APP_NAME: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

---

## Security Best Practices

### 1. Token Storage

**✅ DO:**
- Store access tokens in memory (Vue reactive state) or sessionStorage
- Store refresh tokens in httpOnly cookies (if backend supports) or localStorage with caution

**❌ DON'T:**
- Store tokens in regular cookies (vulnerable to XSS)
- Store tokens in localStorage if you can avoid it (XSS risk)

### 2. HTTPS Only in Production

Always use HTTPS in production to prevent token interception.

### 3. Validate User Input

Always validate and sanitize user input before sending to API.

### 4. Handle Errors Gracefully

Don't expose sensitive error details to users.

### 5. Logout on Token Expiry

Implement automatic logout when refresh token expires.

---

## Testing with Postman/Insomnia

### Example Collection

**1. Register Patient**
```
POST http://localhost:8000/api/v1/users/register/
Content-Type: application/json

{
  "email": "test@example.com",
  "password": "SecurePass123!",
  "password_confirm": "SecurePass123!",
  "first_name": "Test",
  "last_name": "User",
  "lab_client_id": 1
}
```

**2. Login**
```
POST http://localhost:8000/api/v1/auth/login/
Content-Type: application/json

{
  "email": "test@example.com",
  "password": "SecurePass123!"
}
```

**3. Get Studies**
```
GET http://localhost:8000/api/v1/studies/
Authorization: Bearer <access_token>
```

---

## Appendix: TypeScript Type Definitions

**`src/types/api.ts`**
```typescript
export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  phone_number: string | null;
  role: 'patient' | 'lab_staff' | 'lab_manager' | 'admin' | 'doctor';
  lab_client_id: number;
  is_verified: boolean;
  date_joined: string;
}

export interface Study {
  id: number;
  uuid: string;
  order_number: string;
  patient: number;
  patient_detail: {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
  };
  study_type: number;
  study_type_detail: {
    id: number;
    name: string;
    code: string;
    category: string;
    description: string;
    price: string;
  };
  status: 'pending' | 'sample_collected' | 'in_progress' | 'completed' | 'cancelled';
  priority: 'low' | 'normal' | 'high' | 'urgent';
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  results_file: string | null;
  results: string | null;
  notes: string | null;
}

export interface Notification {
  id: number;
  title: string;
  message: string;
  notification_type: 'result_ready' | 'appointment_reminder' | 'payment_due' | 'info';
  channel: 'in_app' | 'email' | 'sms';
  status: 'pending' | 'sent' | 'read' | 'failed';
  created_at: string;
  read_at: string | null;
  related_study_id: number | null;
  metadata: Record<string, any> | null;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiError {
  detail?: string;
  non_field_errors?: string[];
  [key: string]: any;
}
```

---

## Support & Resources

- **Backend API Docs:** http://localhost:8000/api/docs/ (Swagger UI)
- **Backend API Schema:** http://localhost:8000/api/schema/
- **MVP Documentation:** See `MVP.md` in backend repo
- **Security Configuration:** See `SECURITY_CONFIGURATION.md`

---

**Last Updated:** 2025-12-26
**Version:** 1.0
**For:** Vue 3 + Vite Frontend Development
