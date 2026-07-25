/**
 * 페이지 렌더링 및 이벤트 핸들러 모음
 */

const pages = {
    async renderHome() {
        const html = await utils.loadTemplate('home');
        if (state.currentPage !== '/' && state.currentPage !== '/home') return;
        const app = document.getElementById('app');
        app.innerHTML = html;
        
        const actions = document.getElementById('home-actions');
        if (!state.user) {
            actions.innerHTML = '<button onclick="navigate(\'/login\')">로그인하여 시작하기</button>';
        } else if (state.user.role === 'PENDING') {
            actions.innerHTML = '<p>관리자의 승인을 기다리는 중입니다.</p>';
        } else {
            actions.innerHTML = '<button onclick="navigate(\'/patients\')">환자 목록 보기</button>';
        }
    },

    async renderLogin() {
    const html = await utils.loadTemplate('login');
    const app = document.getElementById('app');

    app.innerHTML = html;
    utils.initPasswordToggles(app);
    },

    async renderSignup() {
    const html = await utils.loadTemplate('signup');
    const app = document.getElementById('app');

    app.innerHTML = html;
    utils.initPasswordToggles(app);

    const phoneInput = document.getElementById('signup-phone');

    if (phoneInput) {
        phoneInput.addEventListener(
            'input',
            (e) => utils.handlePhoneInput(e)
        );
    }
},

    async renderPatients(params = {}) {
        const patients = await apis.getPatients(params);
        const html = await utils.loadTemplate('patients');
        if (state.currentPage !== '/patients') return;
        const app = document.getElementById('app');
        app.innerHTML = html;

        // 권한이 있을때만 회원등록 버튼 보이도록
        const createPatientButton = document.getElementById(
            'create-patient-btn'
        );
        if (createPatientButton && canCreatePatient()) {
            createPatientButton.style.display = '';
        }

        // 필드 값 복원
        const nameInput = document.getElementById('search-name');
        const genderSelect = document.getElementById('filter-gender');
        const minAgeInput = document.getElementById('filter-min-age');
        const maxAgeInput = document.getElementById('filter-max-age');

        if (nameInput && params.name) nameInput.value = params.name;
        if (genderSelect && params.gender) genderSelect.value = params.gender;
        if (minAgeInput && params.min_age) minAgeInput.value = params.min_age;
        if (maxAgeInput && params.max_age) maxAgeInput.value = params.max_age;
        
        const listBody = document.getElementById('patients-list');
        if (patients.length === 0) {
            listBody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 2rem;">검색 결과가 없습니다.</td></tr>';
            return;
        }
        listBody.innerHTML = patients.map(p => `
            <tr>
                <td>${p.id}</td>
                <td>${p.name}</td>
                <td>${p.age}</td>
                <td>${p.gender === 'male' ? '남성' : '여성'}</td>
                <td>${utils.formatPhoneNumber(p.phone_number)}</td>
                <td><button onclick="navigate('/patients/${p.id}')">상세보기</button></td>
            </tr>
        `).join('');
    },

    async renderPatientCreate() {
        const html = await utils.loadTemplate('patient-create');
        document.getElementById('app').innerHTML = html;
        
        const phoneInput = document.getElementById('phone_number');
        if (phoneInput) {
            phoneInput.addEventListener('input', (e) => utils.handlePhoneInput(e));
        }
    },

    async renderPatientDetail(patientId) {
        const patient = await apis.getPatient(patientId);
        const records = await apis.getPatientMedicalRecords(patientId);
        const html = await utils.loadTemplate('patient-detail');
        if (!state.currentPage.startsWith('/patients/')) return;
        const app = document.getElementById('app');
        app.innerHTML = html;
        
        // 환자 정보 표시
        document.getElementById('patient-name').innerText = `${patient.name} (${patient.gender === 'male' ? '남성' : '여성'})`;
        document.getElementById('patient-info').innerText = `나이: ${patient.age}세 | 연락처: ${utils.formatPhoneNumber(patient.phone_number)}`;
        
        // 수정 폼 초기값 설정
        document.getElementById('update-name').value = patient.name;
        document.getElementById('update-phone').value = utils.formatPhoneNumber(patient.phone_number);
        
        const updatePhoneInput = document.getElementById('update-phone');
        if (updatePhoneInput) {
            updatePhoneInput.addEventListener('input', (e) => utils.handlePhoneInput(e));
        }
        
        // 버튼 이벤트 바인딩
        document.getElementById('add-record-btn').onclick = () => {
            if (state.user?.department !== 'MEDICAL') {
                window.alert('권한이 없습니다.');
                return;
            }

            navigate(`/patients/${patientId}/medical-records/create`);
        };
        
        // 상세 페이지 전용 상태 (ID 저장)
        state.currentPatientId = patientId;

        const listBody = document.getElementById('records-list');
        listBody.innerHTML = records.map(r => `
            <tr>
                <td>${r.id}</td>
                <td>${r.chart_number}</td>
                <td>${r.symptoms}</td>
                <td>${new Date(r.created_at).toLocaleString()}</td>
                <td><button onclick="navigate('/medical-records/${r.id}')">상세보기</button></td>
            </tr>
        `).join('');
    },

    async renderRecordCreate(patientId) {
        const html = await utils.loadTemplate('record-create');
        const app = document.getElementById('app');
        app.innerHTML = html;
        
        const imageInput = document.getElementById('xray_image');
        const previewContainer = document.getElementById('image-preview-container');

        imageInput.onchange = (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (event) => {
                    previewContainer.innerHTML = `<img src="${event.target.result}" style="max-width: 100%; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">`;
                };
                reader.readAsDataURL(file);
            } else {
                previewContainer.innerHTML = '<p>이미지 미리보기가 여기에 표시됩니다.</p>';
            }
        };

        document.getElementById('record-create-form').onsubmit = (e) => this.handleRecordCreate(e, patientId);
        document.getElementById('cancel-btn').onclick = () => navigate(`/patients/${patientId}`);
    },

    async renderRecordDetail(recordId) {
        const [record, analyses, html] = await Promise.all([
            apis.getMedicalRecord(recordId),
            apis.getMedicalRecordAnalyses(recordId),
            utils.loadTemplate('record-detail')
        ]);
        const app = document.getElementById('app');
        app.innerHTML = html;
        
        document.getElementById('record-id').innerText = record.id;
        document.getElementById('chart-number').innerText = record.chart_number;
        document.getElementById('symptoms-text').innerText = record.symptoms;
        document.getElementById('created-at').innerText = new Date(record.created_at).toLocaleString();
        const xrayImage = record.xray_images?.[0];
        const xrayElement = document.getElementById('xray-img');
        if (xrayImage?.image_url) {
            xrayElement.src = xrayImage.image_url;
        } else {
            xrayElement.removeAttribute('src');
            xrayElement.alt = '등록된 X-Ray 이미지가 없습니다.';
        }
        
        const predictButton = document.getElementById('predict-btn');
        predictButton.addEventListener('click', (event) => {
            event.preventDefault();
            pages.handlePredict(recordId);
        });
        document.getElementById('refresh-analysis-btn').onclick = () => this.renderRecordDetail(recordId);
        document.getElementById('back-to-patient-btn').onclick = () => navigate(`/patients/${record.patient_id}`);
        
        const analysisList = document.getElementById('analysis-list');
        const analysisTable = document.getElementById('analysis-table');
        const analysisEmpty = document.getElementById('analysis-empty');

        if (analyses.length === 0) {
            analysisEmpty.hidden = false;
        } else {
            analysisTable.hidden = false;
            analyses.forEach((analysis) => {
                const row = analysisList.insertRow();
                row.className = analysis.is_pneumonia
                    ? 'result-positive'
                    : 'result-negative';

                row.insertCell().textContent = analysis.id;
                row.insertCell().textContent = analysis.is_pneumonia
                    ? '폐렴 의심'
                    : '정상';
                row.insertCell().textContent = `${Number(analysis.confidence).toFixed(2)}%`;

                const heatmapCell = row.insertCell();
                if (analysis.heatmap_url) {
                    const heatmapResult = document.createElement('div');
                    heatmapResult.className = 'heatmap-result';

                    const heatmapLink = document.createElement('a');
                    heatmapLink.href = analysis.heatmap_url;
                    heatmapLink.target = '_blank';
                    heatmapLink.rel = 'noopener noreferrer';

                    const heatmapImage = document.createElement('img');
                    heatmapImage.src = analysis.heatmap_url;
                    heatmapImage.alt = 'AI Grad-CAM 분석 이미지';
                    heatmapImage.className = 'heatmap-thumb';
                    heatmapLink.appendChild(heatmapImage);

                    const heatmapModel = document.createElement('small');
                    heatmapModel.textContent = analysis.heatmap_model
                        || '모델 정보 없음';

                    heatmapResult.append(heatmapLink, heatmapModel);
                    heatmapCell.appendChild(heatmapResult);
                } else {
                    heatmapCell.textContent = '히트맵 없음';
                }

                row.insertCell().textContent = new Date(
                    analysis.created_at
                ).toLocaleString();
                row.insertCell().textContent = analysis.ai_model;
            });
        }
    },

    async renderMyPage() {
    const html = await utils.loadTemplate('my-page');
    const app = document.getElementById('app');

    app.innerHTML = html;
    utils.initPasswordToggles(app);

    // 기존 현재 사용자 정보 표시 코드...

        // 현재 사용자 정보 표시
        document.getElementById('me-email').innerText = state.user.email;
        document.getElementById('me-name-display').innerText = state.user.name;
        document.getElementById('me-department-display').innerText = state.user.department;
        document.getElementById('me-gender-display').innerText = state.user.gender === 'M' ? '남성' : '여성';
        document.getElementById('me-phone-display').innerText = utils.formatPhoneNumber(state.user.phone_number);
        document.getElementById('me-role-display').innerText = state.user.role;

        // 수정 폼 초기값 설정
        document.getElementById('update-me-department').value = state.user.department;
        document.getElementById('update-me-phone').value = utils.formatPhoneNumber(state.user.phone_number);
        
        const mePhoneInput = document.getElementById('update-me-phone');
        if (mePhoneInput) {
            mePhoneInput.addEventListener('input', (e) => utils.handlePhoneInput(e));
        }

        // 이벤트 바인딩
        document.getElementById('update-me-form').onsubmit = (e) => this.handleUpdateMe(e);
        document.getElementById('update-password-form').onsubmit = (e) => this.handleUpdatePassword(e);
        document.getElementById('delete-me-btn').onclick = () => this.handleDeleteMe();
    },

    async renderAdminUsers(params = {}) {
        const users = await apis.adminGetUsers(params);
        const html = await utils.loadTemplate('admin-users');
        if (state.currentPage !== '/admin/users') return;
        const app = document.getElementById('app');
        app.innerHTML = html;

        // 필드 값 복원
        const queryInput = document.getElementById('admin-search-query');
        const deptSelect = document.getElementById('admin-filter-dept');
        if (queryInput && params.query) queryInput.value = params.query;
        if (deptSelect && params.department) deptSelect.value = params.department;

        const listBody = document.getElementById('admin-users-list');
        // users.map() 실행 전 부서명 매핑 추가 
        const departmentNames = {
            DEV: '개발팀',
            MEDICAL: '의료진',
            RESEARCH: '연구진'
        };

        if (users.length === 0) {
            listBody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 2rem;">검색 결과가 없습니다.</td></tr>';
            return;
        }
        listBody.innerHTML = users.map(u => `
            <tr>
                <td>${u.id}</td>
                <td>${u.name}</td>
                <td>${u.email}</td>
                <td>${departmentNames[u.department] ?? u.department}</td>
                <td>${utils.formatPhoneNumber(u.phone_number)}</td>
                <td>
                    <select onchange="pages.handleRoleUpdate(${u.id}, this.value)" ${u.id === state.user.id ? 'disabled' : ''}>
                        <option value="PENDING" ${u.role === 'PENDING' ? 'selected' : ''}>승인대기</option>
                        <option value="STAFF" ${u.role === 'STAFF' ? 'selected' : ''}>일반회원</option>
                        <option value="ADMIN" ${u.role === 'ADMIN' ? 'selected' : ''}>관리자</option>
                    </select>
                </td>
                <td>${u.is_active ? '<span class="status-badge success">활성</span>' : '<span class="status-badge error">비활성</span>'}</td>
            </tr>
        `).join('');
    },

    // --- Event Handlers ---

    handleAdminSearch() {
        const query = document.getElementById('admin-search-query').value;
        const department = document.getElementById('admin-filter-dept').value;
        
        const params = new URLSearchParams();
        if (query) params.set('query', query);
        if (department) params.set('department', department);
        
        const queryString = params.toString();
        const path = '/admin/users' + (queryString ? '?' + queryString : '');
        navigate(path);
    },

    resetAdminSearch() {
        navigate('/admin/users');
    },

    async handleRoleUpdate(userId, newRole) {
        try {
            await apis.adminUpdateUserRole(userId, { role: newRole });
            utils.showAlert('권한이 변경되었습니다.', 'success');
            this.handleAdminSearch();
        } catch (err) {
            utils.showAlert(`권한 변경 실패: ${err.message}`, 'error');
        }
    },

    async handleUpdateMe(e) {
        e.preventDefault();
        const data = {
            department: document.getElementById('update-me-department').value,
            phone_number: document.getElementById('update-me-phone').value
        };

        try {
            await apis.updateMe(data);
            utils.showAlert('회원 정보가 수정되었습니다.', 'success');
            await checkAuth(); // state 갱신 (app.js)
            this.renderMyPage();
        } catch (err) {
            let msg = err.message;
            if (err.status === 500) msg = '잠시 후 다시시도해주세요.';
            utils.showAlert(msg, 'error', '수정 실패');
        }
    },

    async handleUpdatePassword(e) {
        e.preventDefault();
        const data = {
            current_password: document.getElementById('old-password').value,
            new_password: document.getElementById('new-password').value
        };

        try {
        await apis.updatePassword(data);
        utils.showAlert('비밀번호가 변경되었습니다.', 'success');

        e.target.reset();
        utils.resetPasswordToggles(e.target);
        } catch (err) {
            let msg = err.message;
            if (err.status === 400) {
                msg = '비밀번호는 "대소문자, 특수문자, 숫자를 각 1개씩 포함한 8자리 이상이어야 합니다."';
            } else if (err.status === 500) {
                msg = '잠시 후 다시시도해주세요.';
            }
            utils.showAlert(msg, 'error', '비밀번호 변경 실패');
        }
    },

    async handleDeleteMe() {
        if (!confirm('정말로 탈퇴하시겠습니까? 모든 데이터가 삭제됩니다.')) return;

        try {
            await apis.deleteMe();
            utils.showAlert('탈퇴 처리가 완료되었습니다.', 'success');
            logout(); // (app.js)
        } catch (err) {
            utils.showAlert(`탈퇴 처리 실패: ${err.message}`, 'error');
        }
    },

    async handleLogin(e) {
        e.preventDefault();
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        await login(email, password); // (app.js)
    },

    async handleSignup(e) {
        e.preventDefault();
        const userData = {
            email: document.getElementById('signup-email').value,
            name: document.getElementById('signup-name').value,
            department: document.getElementById('signup-department').value,
            gender: document.getElementById('signup-gender').value,
            phone_number: document.getElementById('signup-phone').value,
            password: document.getElementById('signup-password').value
        };

        try {
            await apis.signup(userData);
            utils.showAlert('회원가입이 완료되었습니다. 로그인해주세요.', 'success');
            navigate('/login');
        } catch (err) {
            let msg = err.message;
            if (err.status === 400 && (msg.includes('비밀번호') || msg.includes('password'))) {
                msg = '비밀번호는 "대소문자, 특수문자, 숫자를 각 1개씩 포함한 8자리 이상이어야 합니다."';
            }
            if (err.status === 500) msg = '잠시 후 다시시도해주세요.';
            utils.showAlert(msg, 'error', '가입 실패');
        }
    },

    async handlePatientCreate(e) {
        e.preventDefault();
        const patientData = {
            name: document.getElementById('name').value,
            age: parseInt(document.getElementById('age').value),
            gender: document.getElementById('gender').value,
            phone_number: document.getElementById('phone_number').value.replace(/[^\d]/g, '')
        };
        
        try {
            await apis.createPatient(patientData);
            utils.showAlert('환자가 등록되었습니다.', 'success');
            navigate('/patients');
        } catch (err) {
            utils.showAlert(`환자 등록 실패: ${err.message}`, 'error');
        }
    },

    handleSearch() {
        const name = document.getElementById('search-name').value;
        const gender = document.getElementById('filter-gender').value;
        const min_age = document.getElementById('filter-min-age').value;
        const max_age = document.getElementById('filter-max-age').value;

        const params = new URLSearchParams();
        if (name) params.set('name', name);
        if (gender) params.set('gender', gender);
        if (min_age) params.set('min_age', min_age);
        if (max_age) params.set('max_age', max_age);

        const queryString = params.toString();
        const path = '/patients' + (queryString ? '?' + queryString : '');
        navigate(path);
    },

    resetSearch() {
        navigate('/patients');
    },

    async handleRecordCreate(e, patientId) {
        e.preventDefault();
        const formData = new FormData();
        formData.append('chart_number', document.getElementById('chart_number').value);
        formData.append('symptoms', document.getElementById('symptoms').value);
        formData.append('shooting_datetime', document.getElementById('shooting_datetime').value);
        formData.append('xray_image', document.getElementById('xray_image').files[0]);

        try {
            await apis.createMedicalRecord(patientId, formData);
            utils.showAlert('진료 기록이 등록되었습니다.', 'success');
            navigate(`/patients/${patientId}`);
        } catch (err) {
            utils.showAlert(`진료 기록 등록 실패: ${err.message}`, 'error');
        }
    },

    async openUpdateModal() {
        try {
            // DB에 저장된 환자 정보를 다시 조회해 수정 폼에 표시
            const patient = await apis.getPatient(state.currentPatientId);

            document.getElementById('update-name').value = patient.name;
            document.getElementById('update-phone').value =
                utils.formatPhoneNumber(patient.phone_number);

            document.getElementById('update-modal').classList.add('show');
        } catch (err) {
            utils.showAlert(`환자 정보 조회 실패: ${err.message}`, 'error');
        }
    },

    closeUpdateModal() {
        document.getElementById('update-modal').classList.remove('show');
    },

    async handlePatientUpdate(e) {
        e.preventDefault();
        const patientId = state.currentPatientId;
        const updateData = {
            name: document.getElementById('update-name').value,
            phone_number: document.getElementById('update-phone').value.replace(/[^\d]/g, '')
        };

        try {
            await apis.updatePatient(patientId, updateData);
            utils.showAlert('환자 정보가 수정되었습니다.', 'success');
            this.closeUpdateModal();
            this.renderPatientDetail(patientId);
        } catch (err) {
            utils.showAlert(`환자 정보 수정 실패: ${err.message}`, 'error');
        }
    },

    confirmDeletePatient() {
        document.getElementById('delete-modal').classList.add('show');
    },

    closeDeleteModal() {
        document.getElementById('delete-modal').classList.remove('show');
    },

    async handlePatientDelete() {
        const patientId = state.currentPatientId;
        try {
            await apis.deletePatient(patientId);
            utils.showAlert('환자 정보와 관련 데이터가 모두 삭제되었습니다.', 'success');
            this.closeDeleteModal();
            navigate('/patients');
        } catch (err) {
            utils.showAlert(`환자 삭제 실패: ${err.message}`, 'error');
        }
    },

    async handlePredict(recordId) {
        const selectedModel = document.getElementById('filter-model')?.value;

        if (!selectedModel) {
            window.alert('모델을 선택해 주세요');
            return;
        }

        if (!['model_1', 'model_3'].includes(selectedModel)) {
            window.alert('지원하지 않는 모델입니다.');
            return;
        }

        const predictButton = document.getElementById('predict-btn');
        const progressContainer = document.getElementById('predict-progress-container');

        if (predictButton) {
            predictButton.disabled = true;
            predictButton.textContent = '예측 중...';
        }
        if (progressContainer) {
            progressContainer.hidden = false;
        }

        try {
            await apis.predictPneumonia(recordId, selectedModel);
            utils.showAlert('AI 예측이 완료되었습니다.', 'success');
            await navigate(`/medical-records/${recordId}`, false);
        } catch (err) {
            utils.showAlert(`AI 예측 실패: ${err.message}`, 'error');
        } finally {
            if (predictButton) {
                predictButton.disabled = false;
                predictButton.textContent = 'AI 예측 결과보기';
            }
            if (progressContainer) {
                progressContainer.hidden = true;
            }
        }
    }
};
