const state = {
    user: null,
    token: localStorage.getItem('token'),
    currentPage: '/'
};

function canViewAnalysis(user) {
    if (!user) return false;
    if (user.role === 'ADMIN') return true;

    return user.role === 'STAFF' && [
        'MEDICAL',
        'DEV',
        'RESEARCH'
    ].includes(user.department);
}

async function login(email, password) {
    const errorEl = document.getElementById('login-error');
    if (errorEl) errorEl.style.display = 'none';

    try {
        const data = await apis.login(email, password);

        if (data && data.status === 401) {
            if (errorEl) errorEl.style.display = 'block';
            return;
        }

        if (data) {
            state.token = data.access_token;
            localStorage.setItem('token', state.token);
            localStorage.setItem('isLoggedIn', 'true');
            await checkAuth();
            
            if (state.user && state.user.role === 'PENDING') {
                navigate('/');
            } else {
                navigate('/patients');
            }
        }
    } catch (err) {
        if (errorEl) {
            errorEl.innerText = err.message || '로그인 중 오류가 발생했습니다.';
            errorEl.style.display = 'block';
        }
    }
}

async function logout(event) {
    if (event) event.preventDefault();
    try {
        if (typeof apis !== 'undefined' && apis.logout) {
            await apis.logout();
            state.token = null;
            state.user = null;
            localStorage.removeItem('token');
            localStorage.removeItem('isLoggedIn');
            updateNav();
            await navigate('/login');
        }
    } catch (err) {
        console.error('Logout failed:', err);
        // 에러가 발생하더라도 클라이언트 측 세션은 정리하고 로그인 페이지로 이동
        state.token = null;
        state.user = null;
        localStorage.removeItem('token');
        localStorage.removeItem('isLoggedIn');
        updateNav();
        navigate('/login');
    }
}

async function checkAuth() {
    if (!state.token && localStorage.getItem('isLoggedIn') === 'true') {
        // 토큰은 없지만 로그인 상태 기록이 있으므로 리프레시 시도
        try {
            const refreshResponse = await apis.refresh();
            if (refreshResponse.ok) {
                const data = await refreshResponse.json();
                state.token = data.access_token;
                localStorage.setItem('token', state.token);
            } else {
                // 리프레시 실패 시 로그인 상태 해제
                localStorage.removeItem('isLoggedIn');
                return;
            }
        } catch (err) {
            return;
        }
    }
    
    if (!state.token) return;
    
    try {
        state.user = await apis.getMe();
        updateNav();
    } catch (err) {
        if (state.token) logout();
    }
}

function updateNav() {
    const authLink = document.getElementById('auth-link');
    const adminLinkContainer = document.getElementById('admin-link-container');
    const emailLogLinkContainer = document.getElementById('email-log-link-container');
    
    if (state.user) {
        document.body.classList.add('logged-in');
        
        if (state.user.role === 'ADMIN') {
            adminLinkContainer.innerHTML = '<a href="/admin/users" onclick="route(event)" class="nav-btn">회원 관리</a>';
            emailLogLinkContainer.innerHTML = state.user.department === 'DEV'
                ? '<a href="/admin/email-logs" onclick="route(event)" class="nav-btn">Email 전송로그</a>'
                : '';
        } else {
            adminLinkContainer.innerHTML = '';
            emailLogLinkContainer.innerHTML = '';
        }
        
        authLink.innerHTML = `
            <span class="user-info" onclick="navigate('/my-page')" style="cursor: pointer;">${state.user.name}(${state.user.department})</span>
            <a href="#" onclick="logout(event)" class="nav-btn logout-btn">로그아웃</a>
        `;
    } else {
        document.body.classList.remove('logged-in');
        adminLinkContainer.innerHTML = '';
        emailLogLinkContainer.innerHTML = '';
        authLink.innerHTML = `<a href="/login" onclick="route(event)" class="nav-btn login-btn">로그인</a>`;
    }
}

function route(event) {
    event.preventDefault();
    const path = event.target.getAttribute('href') || event.currentTarget.getAttribute('href');
    navigate(path);
}
// 환자 등록 권한 확인 함수 추가
function canCreatePatient() {
    return state.user?.role === 'ADMIN' || (
        state.user?.role === 'STAFF' &&
        state.user?.department === 'MEDICAL'
    );
}

async function navigate(path, pushState = true) {
    if (pushState) {
        window.history.pushState({}, "", path);
    }
    
    const url = new URL(window.location.origin + path);
    const pathname = url.pathname;
    const searchParams = Object.fromEntries(url.searchParams);
    
    state.currentPage = pathname;
    const app = document.getElementById('app');
    app.innerHTML = '<div class="card">로딩 중...</div>';

    try {
        // 권한 체크
        const publicPaths = ['/', '/home', '/login', '/signup'];
        if (!state.user && !publicPaths.includes(pathname)) {
            await navigate('/login');
            return;
        }

        if (state.user && state.user.role === 'PENDING' && !publicPaths.includes(pathname) && pathname !== '/my-page') {
            utils.showAlert('승인 대기 중인 사용자입니다. 관리자의 승인 이후에 사용가능합니다.', 'error', '접근 제한');
            await navigate('/');
            return;
        }

        if (pathname.startsWith('/admin/') && state.user?.role !== 'ADMIN') {
            utils.showAlert('관리자 권한이 필요합니다.', 'error', '접근 제한');
            await navigate('/');
            return;
        }
        if (
            pathname === '/admin/email-logs'
            && !(
                state.user?.role === 'ADMIN'
                && state.user?.department === 'DEV'
            )
        ) {
            utils.showAlert(
                '개발팀 관리자만 접근할 수 있습니다.',
                'error',
                '접근 제한'
            );
            await navigate('/');
            return;
        }
        // 환자 등록 주소 직접접근 차단
        if (pathname === '/patients/create' && !canCreatePatient()) {
            utils.showAlert(
                '환자 등록은 의료 부서 스태프만 가능합니다.',
                'error',
                '접근 제한'
            );
            await navigate('/patients');
            return;
        }

        if (pathname.startsWith('/medical-records/') && !canViewAnalysis(state.user)) {
            utils.showAlert('AI 예측 결과 조회 권한이 없습니다.', 'error', '접근 제한');
            await navigate('/');
            return;
        }

        if (pathname === '/' || pathname === '/home') {
            await pages.renderHome();
        } else if (pathname === '/login') {
            await pages.renderLogin();
        } else if (pathname === '/signup') {
            await pages.renderSignup();
        } else if (pathname === '/patients') {
            await pages.renderPatients(searchParams);
        } else if (pathname === '/patients/create') {
            await pages.renderPatientCreate();
        } else if (pathname.startsWith('/patients/') && pathname.endsWith('/medical-records/create')) {
            const patientId = pathname.split('/')[2];
            await pages.renderRecordCreate(patientId);
        } else if (pathname === '/my-page') {
            pages.renderMyPage();
        } else if (pathname === '/admin/users') {
            await pages.renderAdminUsers(searchParams);
        } else if (pathname === '/admin/email-logs') {
            await pages.renderAdminEmailLogs(searchParams);
        } else if (pathname.startsWith('/patients/')) {
            const patientId = pathname.split('/')[2];
            await pages.renderPatientDetail(patientId);
        } else if (pathname.startsWith('/medical-records/')) {
            const recordId = pathname.split('/')[2];
            await pages.renderRecordDetail(recordId);
        } else {
            app.innerHTML = '<div class="card"><h2>404</h2><p>페이지를 찾을 수 없습니다.</p></div>';
        }
    } catch (err) {
        app.innerHTML = `<div class="card"><h2>오류</h2><p>${err.message}</p><button onclick="navigate('/')">홈으로</button></div>`;
    }
}

window.onpopstate = () => {
    navigate(window.location.pathname + window.location.search, false);
};

document.addEventListener('DOMContentLoaded', () => {
    checkAuth().then(() => {
        navigate(window.location.pathname + window.location.search, false);
    });
});
