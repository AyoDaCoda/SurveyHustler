const BACKEND_URL = 'https://2dd3d5aa0786.ngrok-free.app';
let academicData = {};

let registrationData = {
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    gender: '',
    password: '', // Store password temporarily for resend OTP
    tg_id: '' // Assuming tg_id is also part of initial registration and might be needed for resend
};

// Function to show/hide steps
function showStep(stepNumber) {
    document.querySelectorAll('.step').forEach(step => {
        step.classList.add('hidden');
    });
    document.querySelector(`.step-${stepNumber}`).classList.remove('hidden');
}

// Initial state: show step 1
document.addEventListener('DOMContentLoaded', async () => { // ADD async
    showStep(1);
    document.getElementById('step1Error').textContent = '';
    document.getElementById('otpError').textContent = '';
    document.getElementById('otpMessage').textContent = '';
    document.getElementById('step2Error').textContent = '';

    await loadAcademicOptions(); // NEW: Load academic data on page load
});

// NEW: Function to load academic hierarchy data
async function loadAcademicOptions() {
    try {
        const res = await fetch(`${BACKEND_URL}/api/options`);
        if (!res.ok) {
            throw new Error(`HTTP error! status: ${res.status}`);
        }
        academicData = await res.json();
        populateInstitutions(); // Populate the first dropdown
    } catch (error) {
        console.error("Error loading academic options:", error);
        displayError('step2Error', 'Failed to load academic options. Please refresh.');
    }
}
// END NEW

// Helper to display error messages
function displayError(elementId, message) {
    const errorDiv = document.getElementById(elementId);
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.color = 'red';
        errorDiv.style.fontWeight = 'bold';
    }
}

// Helper to display success messages
function displayMessage(elementId, message) {
    const msgDiv = document.getElementById(elementId);
    if (msgDiv) {
        msgDiv.textContent = message;
        msgDiv.style.color = 'green';
        msgDiv.style.fontWeight = 'bold';
    }
}

// NEW: Dropdown population and event listener functions
function populateDropdown(selectElementId, options, defaultText) {
    const selectElement = document.getElementById(selectElementId);
    selectElement.innerHTML = `<option value="">${defaultText}</option>`;
    options.forEach(option => {
        const opt = document.createElement('option');
        opt.value = option.value !== undefined ? option.value : option.id; // Handle both name (for hierarchy) and value (for levels)
        opt.textContent = option.name;
        selectElement.appendChild(opt);
    });
    selectElement.disabled = false;
}

function clearAndDisable(elements) {
    elements.forEach(id => {
        const el = document.getElementById(id);
        el.innerHTML = `<option value="">Select ${id.charAt(0).toUpperCase() + id.slice(1)}</option>`;
        el.disabled = true;
    });
}

function populateInstitutions() {
    populateDropdown('institution', academicData.institutions, 'Select Institution');
    document.getElementById('institution').addEventListener('change', onInstitutionChange);
    clearAndDisable(['college', 'department', 'course', 'level']);
}

function onInstitutionChange() {
    const selectedInstitutionId = document.getElementById('institution').value;
    const selectedInstitution = academicData.institutions.find(inst => inst.id === parseInt(selectedInstitutionId));

    clearAndDisable(['college', 'department', 'course', 'level']);

    if (selectedInstitution) {
        populateDropdown('college', selectedInstitution.colleges, 'Select College');
        document.getElementById('college').addEventListener('change', onCollegeChange);
    }
}

function onCollegeChange() {
    const selectedInstitutionId = document.getElementById('institution').value;
    const selectedCollegeId = document.getElementById('college').value;
    const selectedInstitution = academicData.institutions.find(inst => inst.id === parseInt(selectedInstitutionId));
    const selectedCollege = selectedInstitution?.colleges.find(col => col.id === parseInt(selectedCollegeId));

    clearAndDisable(['department', 'course', 'level']);

    if (selectedCollege) {
        populateDropdown('department', selectedCollege.departments, 'Select Department');
        document.getElementById('department').addEventListener('change', onDepartmentChange);
    }
}

function onDepartmentChange() {
    const selectedInstitutionId = document.getElementById('institution').value;
    const selectedCollegeId = document.getElementById('college').value;
    const selectedDepartmentId = document.getElementById('department').value; // Get the ID (as a string)

    const selectedInstitution = academicData.institutions.find(inst => inst.id === parseInt(selectedInstitutionId));
    const selectedCollege = selectedInstitution?.colleges.find(col => col.id === parseInt(selectedCollegeId));
    // Find the department in the selected college's departments by its ID
    const selectedDepartment = selectedCollege?.departments.find(dept => dept.id === parseInt(selectedDepartmentId));

    clearAndDisable(['course', 'level']); // Clear and disable both

    if (selectedDepartment) {
        populateDropdown('course', selectedDepartment.courses, 'Select Course (Optional)');
        document.getElementById('course').addEventListener('change', onCourseChange);
        // Do NOT populate levels here, as they are course-specific now.
        // User must select a course first.
    }
}

function onCourseChange() {
    const selectedInstitutionId = document.getElementById('institution').value;
    const selectedCollegeId = document.getElementById('college').value;
    const selectedDepartmentId = document.getElementById('department').value;
    const selectedCourseId = document.getElementById('course').value; // Get the ID (as a string)

    const selectedInstitution = academicData.institutions.find(inst => inst.id === parseInt(selectedInstitutionId));
    const selectedCollege = selectedInstitution?.colleges.find(col => col.id === parseInt(selectedCollegeId));
    const selectedDepartment = selectedCollege?.departments.find(dept => dept.id === parseInt(selectedDepartmentId));
    // Find the course in the selected department's courses by its ID
    const selectedCourse = selectedDepartment?.courses.find(course => course.id === parseInt(selectedCourseId));

    clearAndDisable(['level']); // Only clear and disable level

    if (selectedCourse) {
        // Filter levels based on the selected course
        const levelsForCourse = selectedCourse.levels.map(val => ({value: val, name: val}));
        populateDropdown('level', levelsForCourse, 'Select Level');
    } else {
        // If course is optional AND no course is selected, levels should be disabled.
        // The backend now requires a course for level selection.
        clearAndDisable(['level']);
    }
}

// Get a reference to the resend link element
const resendOtpLink = document.getElementById('resendOtpLink');
let countdownIntervalId; // Variable to hold the interval ID for clearing
const initialCountdownTime = 30; // seconds

function startCountdown(duration){
    let timer = duration;

    // Clear any existing countdown to prevent multiple timers running
    if (countdownIntervalId) {
        clearInterval(countdownIntervalId);
    }

    // Immediately set the state for inactive link
    resendOtpLink.classList.remove('active');
    resendOtpLink.classList.add('inactive');
    resendOtpLink.style.pointerEvents = 'none'; // Disable clicking during countdown
    resendOtpLink.textContent = `Resend in ${timer}s`; // Display initial countdown value

    countdownIntervalId = setInterval(() => {
        if (timer > 0) {
            timer--; // Decrement first, then display
            resendOtpLink.textContent = `Resend in ${timer}s`;
        } else {
            clearInterval(countdownIntervalId);
            resendOtpLink.textContent = 'Resend OTP';
            resendOtpLink.classList.remove('inactive');
            resendOtpLink.classList.add('active');
            resendOtpLink.style.pointerEvents = 'auto'; // Enable clicking
        }
    }, 1000); // Update every 1 second
}

// Function to resend OTP (similar to sendOtp but without basic info validation)
async function sendNewOtpRequest() {
    const { email, first_name, last_name, phone, gender, password, tg_id } = registrationData;

    console.log("Attempting to resend OTP with stored data:", registrationData);

    if (!email || !password || !first_name || !last_name || !phone || !gender) {
        displayError('otpError', 'Email is missing. Please go back to Step 1.');
        if (resendOtpLink) {
             resendOtpLink.classList.remove('inactive');
             resendOtpLink.classList.add('active');
             resendOtpLink.style.pointerEvents = 'auto';
             resendOtpLink.textContent = 'Resend OTP'; // Revert text
        }
        return;
    }

    displayMessage('otpMessage', 'Resending OTP...');
    displayError('otpError', ''); // Clear previous errors

    try {
        const res = await fetch(`${BACKEND_URL}/api/send_otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email,
                password,
                first_name,
                last_name,
                phone,
                gender,
                tg_id // tg_id is optional for backend validation but good to send if available
            })
        });

        const result = await res.json();
        console.log("Resend OTP API response:", res.status, result);

        if (res.ok) {
            displayMessage('otpMessage', result.message);
            startCountdown(initialCountdownTime);
        } else {
            displayError('otpError', result.message || 'Failed to resend OTP.');

            if (resendOtpLink) {
                 resendOtpLink.classList.remove('inactive');
                 resendOtpLink.classList.add('active');
                 resendOtpLink.style.pointerEvents = 'auto';
                 resendOtpLink.textContent = 'Resend OTP'; // Revert text
            }
        }
    } catch (err) {
        console.error('Error resending OTP:', err);
        displayError('otpError', 'Network error. Please try again.');

        if (resendOtpLink) {
             resendOtpLink.classList.remove('inactive');
             resendOtpLink.classList.add('active');
             resendOtpLink.style.pointerEvents = 'auto';
             resendOtpLink.textContent = 'Resend OTP'; // Revert text
        }
    }
}

// --- Function to Send Initial OTP (Crucial for starting countdown) ---
async function sendOtp() {
    // Collect data from inputs
    const first_name_val = document.getElementById("first_name").value;
    const last_name_val = document.getElementById("last_name").value;
    const email_val = document.getElementById("email").value;
    const phone_val = document.getElementById("phone").value;
    const gender_val = document.getElementById("gender").value;
    const password_val = document.getElementById("password").value;
    const confirmPassword_val = document.getElementById("confirm_password").value;
    const tg_id_val = document.getElementById("tg_id").value;

    // Clear previous errors/messages
    displayError('step1Error', '');
    displayError('otpError', '');
    displayMessage('otpMessage', '');

    // Basic client-side validation for step 1
    if (!first_name_val || !last_name_val || !email_val || !phone_val || !gender_val || !password_val || !confirmPassword_val) {
        displayError('step1Error', 'Please fill in all personal information fields.');
        return;
    }
    if (password_val !== confirmPassword_val) {
        displayError('step1Error', 'Passwords do not match.');
        return;
    }
    if (password_val.length < 6) {
        displayError('step1Error', 'Password must be at least 6 characters long.');
        return;
    }

    try {
        const res = await fetch(`${BACKEND_URL}/api/send_otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tg_id: tg_id_val,
                first_name: first_name_val,
                last_name: last_name_val,
                email: email_val,
                phone: phone_val,
                gender: gender_val,
                password: password_val
            })
        });

        const result = await res.json();

        if (res.ok) {
            displayMessage('otpMessage', result.message);
            document.getElementById('display_email').textContent = email_val; // Show email in OTP step
            showStep('otp'); // Move to OTP verification step

            // *** IMPORTANT: Store personal details in a global variable for later use ***
            registrationData.first_name = first_name_val;
            registrationData.last_name = last_name_val;
            registrationData.email = email_val;
            registrationData.phone = phone_val;
            registrationData.gender = gender_val;
            registrationData.password = password_val; // Store password temporarily for resend
            registrationData.tg_id = tg_id_val;

            console.log("Stored registrationData:", registrationData);
            // *** IMPORTANT: START THE COUNTDOWN HERE AFTER SUCCESSFULLY SHOWING THE OTP STEP ***
            startCountdown(initialCountdownTime);
        } else {
            displayError('step1Error', result.message || 'Failed to send OTP.');
        }
    } catch (err) {
        console.error('Error sending OTP:', err);
        displayError('step1Error', 'Network error. Please try again.');
    }
}

async function verifyOtp() {
    const email = registrationData.email;
    const otp = document.getElementById("otp_input").value;

    // Clear previous errors/messages
    displayError('otpError', '');
    displayMessage('otpMessage', '');

    if (!email) {
        displayError('otpError', 'Email data missing for verification. Please go back to Step 1.');
        return;
    }
    if (otp.length !== 6 || !/^\d+$/.test(otp)) {
        displayError('otpError', 'Please enter a valid 6-digit OTP.');
        return;
    }

    try {
        const res = await fetch(`${BACKEND_URL}/api/verify_otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, otp_code: otp })
        });

        const result = await res.json();

        if (res.ok) {
            displayMessage('otpMessage', result.message);
            showStep(2); // Move to academic information step
            displayError('step2Error', ''); // Clear any previous academic errors
        } else {
            displayError('otpError', result.message || 'OTP verification failed.');
        }
    } catch (err) {
        console.error('Error verifying OTP:', err);
        displayError('otpError', 'Network error. Please try again.');
        displayError('otpError', 'Network error. Please try again.');
    }
}

// Attach the event listener once the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Check if the element exists to prevent errors on other pages
    if (resendOtpLink) {
        resendOtpLink.addEventListener('click', () => {
            // Only trigger the request if the link is active (countdown is done)
            if (resendOtpLink.classList.contains('active')) {
                sendNewOtpRequest(); // Call the function that sends the OTP
            }
        });
    }
});


// Function to submit the final registration form (collects ALL data now)
async function submitForm() {
    // Collect data from Step 1
    const tg_id = document.getElementById("tg_id").value;
    const first_name = document.getElementById("first_name").value;
    const last_name = document.getElementById("last_name").value;
    const email = document.getElementById("email").value;
    const phone = document.getElementById("phone").value;
    const gender = document.getElementById("gender").value;
    const password = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirm_password").value; // For client-side check

    // Collect data from Step 2
    const institution = document.getElementById("institution").value;
    const role = document.getElementById("role").value;
    const college = document.getElementById("college").value;
    const level = document.getElementById("level").value;
    const department = document.getElementById("department").value;
    const course = document.getElementById("course").value; // This can be empty

    // Clear previous errors
    displayError('step2Error', '');

    // Basic client-side validation for step 2
    if (!institution || !role || !college || !level || !department) {
        displayError('step2Error', 'Please fill in all required academic information fields.');
        return;
    }

    // Combine all data into a single object for the final API call
    const data = {
        tg_id,
        first_name,
        last_name,
        email,
        phone,
        gender,
        password, // The backend will hash this
        institution,
        role,
        college,
        level,
        department,
        course
    };

    try {
        const res = await fetch(`${BACKEND_URL}/api/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await res.json();

        if (res.ok) {
            showStep(3); // Registration successful!
        } else {
            displayError('step2Error', result.message || 'Registration failed.');
        }
    } catch (err) {
        console.error('Error during final registration:', err);
        displayError('step2Error', 'Network error during registration. Please try again.');
    }
}
