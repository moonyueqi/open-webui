<script lang="ts">
	import DOMPurify from 'dompurify';
	import { marked } from 'marked';

	import { toast } from 'svelte-sonner';

	import { onMount, getContext, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { getBackendConfig } from '$lib/apis';
	import {
		ldapUserSignIn,
		getSessionUser,
		userSignIn,
		userSignUp,
		updateUserTimezone
	} from '$lib/apis/auths';

	import { WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';
	import { WEBUI_NAME, config, user, socket } from '$lib/stores';

	import { generateInitialsImage, canvasPixelTest, getUserTimezone } from '$lib/utils';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import { redirect } from '@sveltejs/kit';

	const i18n = getContext('i18n');

	let loaded = false;
	let signingIn = false;

	let mode = $config?.features.enable_ldap ? 'ldap' : 'signin';

	let form = null;

	let name = '';
	let email = '';
	let password = '';
	let confirmPassword = '';

	let ldapUsername = '';

	const setSessionUser = async (sessionUser, redirectPath: string | null = null) => {
		if (sessionUser) {
			console.log(sessionUser);
			signingIn = true;
			toast.success($i18n.t(`You're now logged in.`));
			if (sessionUser.token) {
				localStorage.token = sessionUser.token;
			}
			$socket.emit('user-join', { auth: { token: sessionUser.token } });
			await user.set(sessionUser);

			if (!redirectPath) {
				redirectPath = $page.url.searchParams.get('redirect') || '/';
			}

			goto(redirectPath);
			localStorage.removeItem('redirectPath');

			await config.set(await getBackendConfig());

			const timezone = getUserTimezone();
			if (sessionUser.token && timezone) {
				updateUserTimezone(sessionUser.token, timezone);
			}
		}
	};

	const signInHandler = async () => {
		const sessionUser = await userSignIn(email, password).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		await setSessionUser(sessionUser);
	};

	const signUpHandler = async () => {
		if ($config?.features?.enable_signup_password_confirmation) {
			if (password !== confirmPassword) {
				toast.error($i18n.t('Passwords do not match.'));
				return;
			}
		}

		const sessionUser = await userSignUp(name, email, password, generateInitialsImage(name)).catch(
			(error) => {
				toast.error(`${error}`);
				return null;
			}
		);

		await setSessionUser(sessionUser);
	};

	const ldapSignInHandler = async () => {
		const sessionUser = await ldapUserSignIn(ldapUsername, password).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
		await setSessionUser(sessionUser);
	};

	const validateEmail = (email: string): boolean => {
		const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$/;
		return emailRegex.test(email.trim());
	};

	const validatePassword = (password: string): boolean => {
		const hasLetter = /[a-zA-Z]/.test(password);
		const hasDigit = /\d/.test(password);
		return password.length >= 6 && hasLetter && hasDigit;
	};

	const submitHandler = async () => {
		if (mode === 'signup') {
			if (!name.trim()) {
				toast.error($i18n.t('Please enter your name.'));
				return;
			}
		}

		if (mode === 'ldap') {
			if (!ldapUsername.trim()) {
				toast.error($i18n.t('Please enter your username.'));
				return;
			}
		} else {
			if (!email.trim()) {
				toast.error($i18n.t('Please enter your email.'));
				return;
			}
			if (!validateEmail(email)) {
				toast.error($i18n.t('Please enter a valid email address.'));
				return;
			}
		}

		if (!password) {
			toast.error($i18n.t('Please enter your password.'));
			return;
		}

		if (mode === 'signup') {
			if (!validatePassword(password)) {
				toast.error($i18n.t('Password must be at least 6 characters and contain both letters and numbers.'));
				return;
			}
		}

		if (mode === 'ldap') {
			await ldapSignInHandler();
		} else if (mode === 'signin') {
			await signInHandler();
		} else {
			await signUpHandler();
		}
	};

	const oauthCallbackHandler = async () => {
		// Get the value of the 'token' cookie
		function getCookie(name) {
			const match = document.cookie.match(
				new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)')
			);
			return match ? decodeURIComponent(match[1]) : null;
		}

		const token = getCookie('token');
		if (!token) {
			return;
		}

		const sessionUser = await getSessionUser(token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (!sessionUser) {
			return;
		}

		localStorage.token = token;
		await setSessionUser(sessionUser, localStorage.getItem('redirectPath') || null);
	};

	async function setLogoImage() {
		await tick();
		const logo = document.getElementById('logo');

		if (logo) {
			const isDarkMode = document.documentElement.classList.contains('dark');

			if (isDarkMode) {
				const darkImage = new Image();
				darkImage.src = `${WEBUI_BASE_URL}/static/auth-form-logo-dark.png`;

				darkImage.onload = () => {
					logo.src = `${WEBUI_BASE_URL}/static/auth-form-logo-dark.png`;
					logo.style.filter = '';
				};

				darkImage.onerror = () => {
					logo.style.filter = 'invert(1)';
				};
			}
		}
	}

	onMount(async () => {
		const redirectPath = $page.url.searchParams.get('redirect');
		if ($user !== undefined) {
			goto(redirectPath || '/');
		} else {
			if (redirectPath) {
				localStorage.setItem('redirectPath', redirectPath);
			}
		}

		const error = $page.url.searchParams.get('error');
		if (error) {
			toast.error(error);
		}

		await oauthCallbackHandler();
		form = $page.url.searchParams.get('form');

		loaded = true;
		setLogoImage();

		if (($config?.features.auth_trusted_header ?? false) || $config?.features.auth === false) {
			await signInHandler();
		} else if ($config?.onboarding ?? false) {
			mode = $config?.features.enable_ldap ? 'ldap' : 'signup';
		}
	});
</script>

<svelte:head>
	<title>
		{`${$WEBUI_NAME}`}
	</title>
</svelte:head>


<div class="w-full h-screen max-h-[100dvh] text-white relative" id="auth-page">
	<div class="w-full h-full absolute top-0 left-0 bg-gradient-to-br from-[#e0ecff] via-[#d6e4ff] to-[#c7d7fe] dark:from-gray-900 dark:via-gray-900 dark:to-gray-900"></div>

	<div class="w-full absolute top-0 left-0 right-0 h-8 drag-region" />

	{#if signingIn}
		<div
			class="fixed inset-0 z-[200] flex items-center justify-center bg-white dark:bg-black"
		>
			<img
				crossorigin="anonymous"
				src="{WEBUI_BASE_URL}/static/splash.png"
				class="h-24 w-auto object-contain dark:hidden"
				alt="Logo"
			/>
			<img
				crossorigin="anonymous"
				src="{WEBUI_BASE_URL}/static/splash-dark.png"
				class="h-24 w-auto object-contain hidden dark:block"
				alt="Logo"
			/>
		</div>
	{/if}

	{#if loaded}
		<div
			class="fixed min-h-screen w-full flex justify-center font-primary z-50 text-black dark:text-white"
			id="auth-container"
		>
			<div class="fixed top-6 left-8 z-50">
				<div class="flex items-center space-x-3">
					<img
						crossorigin="anonymous"
						src="{WEBUI_BASE_URL}/static/auth-logo.png"
						class="h-14 w-auto object-contain"
						alt="Logo"
					/>
				</div>
			</div>

			<div class="w-full px-10 min-h-screen flex flex-col text-center justify-center items-center">
				{#if ($config?.features.auth_trusted_header ?? false) || $config?.features.auth === false}
					<div class="pb-10 w-full sm:max-w-md bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8">
						<div
							class="flex items-center justify-center gap-3 text-xl sm:text-2xl text-center font-medium dark:text-gray-200"
						>
							<div>
								{$i18n.t('Signing in to {{WEBUI_NAME}}', { WEBUI_NAME: $WEBUI_NAME })}
							</div>

							<div>
								<Spinner className="size-5" />
							</div>
						</div>
					</div>
				{:else}
					<div class="flex flex-col justify-center items-center w-full">
						<div class="sm:max-w-md w-full bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8">
							<div class="flex justify-center mb-3">
								<img
									id="logo"
									crossorigin="anonymous"
									src="{WEBUI_BASE_URL}/static/auth-form-logo.png"
									class="h-16 w-auto object-contain"
									alt="{$WEBUI_NAME} logo"
								/>
							</div>
							<form
								class="flex flex-col justify-center"
								novalidate
								on:submit={(e) => {
									e.preventDefault();
									submitHandler();
								}}
							>
								<div class="mb-1">
									{#if $config?.onboarding ?? false}
									{/if}
								</div>

								{#if $config?.features.enable_login_form || $config?.features.enable_ldap || form}
									<div class="flex flex-col mt-4">
										{#if mode === 'signup'}
											<div class="mb-2">
												<label for="name" class="text-sm font-medium text-left mb-1 block text-gray-700 dark:text-gray-300"
													>{$i18n.t('Name')}</label
												>
												<input
													bind:value={name}
													type="text"
													id="name"
													class="my-0.5 w-full text-sm outline-hidden bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 placeholder:text-gray-400 dark:placeholder:text-gray-500 text-gray-800 dark:text-gray-200"
													autocomplete="name"
													placeholder={$i18n.t('Enter Your Full Name')}
												/>
											</div>
										{/if}

										{#if mode === 'ldap'}
											<div class="mb-2">
												<label for="username" class="text-sm font-medium text-left mb-1 block text-gray-700 dark:text-gray-300"
													>{$i18n.t('Username')}</label
												>
												<input
													bind:value={ldapUsername}
													type="text"
													class="my-0.5 w-full text-sm outline-hidden bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 placeholder:text-gray-400 dark:placeholder:text-gray-500 text-gray-800 dark:text-gray-200"
													autocomplete="username"
													name="username"
													id="username"
													placeholder={$i18n.t('Enter Your Username')}
												/>
											</div>
										{:else}
											<div class="mb-2">
												<label for="email" class="text-sm font-medium text-left mb-1 block text-gray-700 dark:text-gray-300"
													>{$i18n.t('Email')}</label
												>
												<input
													bind:value={email}
													type="text"
													id="email"
													class="my-0.5 w-full text-sm outline-hidden bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 placeholder:text-gray-400 dark:placeholder:text-gray-500 text-gray-800 dark:text-gray-200"
													autocomplete="email"
													name="email"
													placeholder={$i18n.t('Enter Your Email')}
												/>
											</div>
										{/if}

										<div>
											<label for="password" class="text-sm font-medium text-left mb-1 block text-gray-700 dark:text-gray-300"
												>{$i18n.t('Password')}</label
											>
											<SensitiveInput
												bind:value={password}
												type="password"
												id="password"
												outerClassName="flex flex-1 my-0.5 w-full bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2"
												inputClassName="w-full text-sm bg-transparent placeholder:text-gray-400 dark:placeholder:text-gray-500 text-gray-800 dark:text-gray-200 outline-hidden"
												showButtonClassName="pl-1.5 transition bg-transparent text-gray-500 dark:text-gray-400"
												placeholder={$i18n.t('Enter Your Password')}
												autocomplete={mode === 'signup' ? 'new-password' : 'current-password'}
												screenReader={true}
												required={false}
											/>
										</div>

										{#if mode === 'signup' && $config?.features?.enable_signup_password_confirmation}
											<div class="mt-2">
												<label
													for="confirm-password"
													class="text-sm font-medium text-left mb-1 block text-gray-700 dark:text-gray-300"
													>{$i18n.t('Confirm Password')}</label
												>
												<SensitiveInput
													bind:value={confirmPassword}
													type="password"
													id="confirm-password"
													outerClassName="flex flex-1 my-0.5 w-full bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2"
													inputClassName="w-full text-sm bg-transparent placeholder:text-gray-400 dark:placeholder:text-gray-500 text-gray-800 dark:text-gray-200 outline-hidden"
													showButtonClassName="pl-1.5 transition bg-transparent text-gray-500 dark:text-gray-400"
													placeholder={$i18n.t('Confirm Your Password')}
													autocomplete="new-password"
													required={false}
												/>
											</div>
										{/if}
									</div>
								{/if}
								<div class="mt-5">
									{#if $config?.features.enable_login_form || $config?.features.enable_ldap || form}
										{#if mode === 'ldap'}
											<button
												class="bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] hover:from-[#5558e6] hover:to-[#7c4feb] text-white transition w-full rounded-xl font-medium text-sm py-2.5 shadow-md"
												type="submit"
											>
												{$i18n.t('Authenticate')}
											</button>
										{:else}
											<button
												class="bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] hover:from-[#5558e6] hover:to-[#7c4feb] text-white transition w-full rounded-xl font-medium text-sm py-2.5 shadow-md"
												type="submit"
											>
												{mode === 'signin'
													? $i18n.t('Sign in')
													: ($config?.onboarding ?? false)
														? $i18n.t('Create Admin Account')
														: $i18n.t('Create Account')}
											</button>

											{#if $config?.features.enable_signup && !($config?.onboarding ?? false)}
												<div class="mt-4 text-sm text-center text-gray-600 dark:text-gray-400">
													{mode === 'signin'
														? $i18n.t("Don't have an account?")
														: $i18n.t('Already have an account?')}

													<button
														class="font-medium underline text-[#6366f1] hover:text-[#8b5cf6]"
														type="button"
														on:click={() => {
															if (mode === 'signin') {
																mode = 'signup';
															} else {
																mode = 'signin';
															}
														}}
													>
														{mode === 'signin' ? $i18n.t('Sign up') : $i18n.t('Sign in')}
													</button>
												</div>
											{/if}
										{/if}
									{/if}
								</div>
							</form>

							{#if Object.keys($config?.oauth?.providers ?? {}).length > 0}
								<div class="inline-flex items-center justify-center w-full">
									<hr class="w-32 h-px my-4 border-0 bg-gray-200 dark:bg-gray-600" />
									{#if $config?.features.enable_login_form || $config?.features.enable_ldap || form}
										<span
											class="px-3 text-sm font-medium text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800"
											>{$i18n.t('or')}</span
										>
									{/if}

									<hr class="w-32 h-px my-4 border-0 bg-gray-200 dark:bg-gray-600" />
								</div>
								<div class="flex flex-col space-y-2">
									{#if $config?.oauth?.providers?.google}
										<button
											class="flex justify-center items-center bg-gray-50 hover:bg-gray-100 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 dark:hover:text-white transition w-full rounded-full font-medium text-sm py-2.5 border border-gray-200 dark:border-gray-600"
											on:click={() => {
												window.location.href = `${WEBUI_BASE_URL}/oauth/google/login`;
											}}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 48 48"
												class="size-6 mr-3"
												aria-hidden="true"
											>
												<path
													fill="#EA4335"
													d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
												/><path
													fill="#4285F4"
													d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
												/><path
													fill="#FBBC05"
													d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
												/><path
													fill="#34A853"
													d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
												/><path fill="none" d="M0 0h48v48H0z" />
											</svg>
											<span>{$i18n.t('Continue with {{provider}}', { provider: 'Google' })}</span>
										</button>
									{/if}
									{#if $config?.oauth?.providers?.microsoft}
										<button
											class="flex justify-center items-center bg-gray-50 hover:bg-gray-100 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 dark:hover:text-white transition w-full rounded-full font-medium text-sm py-2.5 border border-gray-200 dark:border-gray-600"
											on:click={() => {
												window.location.href = `${WEBUI_BASE_URL}/oauth/microsoft/login`;
											}}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 21 21"
												class="size-6 mr-3"
												aria-hidden="true"
											>
												<rect x="1" y="1" width="9" height="9" fill="#f25022" /><rect
													x="1"
													y="11"
													width="9"
													height="9"
													fill="#00a4ef"
												/><rect x="11" y="1" width="9" height="9" fill="#7fba00" /><rect
													x="11"
													y="11"
													width="9"
													height="9"
													fill="#ffb900"
												/>
											</svg>
											<span>{$i18n.t('Continue with {{provider}}', { provider: 'Microsoft' })}</span
											>
										</button>
									{/if}
									{#if $config?.oauth?.providers?.github}
										<button
											class="flex justify-center items-center bg-gray-50 hover:bg-gray-100 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 dark:hover:text-white transition w-full rounded-full font-medium text-sm py-2.5 border border-gray-200 dark:border-gray-600"
											on:click={() => {
												window.location.href = `${WEBUI_BASE_URL}/oauth/github/login`;
											}}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 24 24"
												class="size-6 mr-3"
												aria-hidden="true"
											>
												<path
													fill="currentColor"
													d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.92 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57C20.565 21.795 24 17.31 24 12c0-6.63-5.37-12-12-12z"
												/>
											</svg>
											<span>{$i18n.t('Continue with {{provider}}', { provider: 'GitHub' })}</span>
										</button>
									{/if}
									{#if $config?.oauth?.providers?.oidc}
										<button
											class="flex justify-center items-center bg-gray-50 hover:bg-gray-100 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 dark:hover:text-white transition w-full rounded-full font-medium text-sm py-2.5 border border-gray-200 dark:border-gray-600"
											on:click={() => {
												window.location.href = `${WEBUI_BASE_URL}/oauth/oidc/login`;
											}}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												fill="none"
												viewBox="0 0 24 24"
												stroke-width="1.5"
												stroke="currentColor"
												class="size-6 mr-3"
												aria-hidden="true"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z"
												/>
											</svg>

											<span
												>{$i18n.t('Continue with {{provider}}', {
													provider: $config?.oauth?.providers?.oidc ?? 'SSO'
												})}</span
											>
										</button>
									{/if}
									{#if $config?.oauth?.providers?.feishu}
										<button
											class="flex justify-center items-center bg-gray-50 hover:bg-gray-100 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 dark:hover:text-white transition w-full rounded-full font-medium text-sm py-2.5 border border-gray-200 dark:border-gray-600"
											on:click={() => {
												window.location.href = `${WEBUI_BASE_URL}/oauth/feishu/login`;
											}}
										>
											<span>{$i18n.t('Continue with {{provider}}', { provider: 'Feishu' })}</span>
										</button>
									{/if}
								</div>
							{/if}

							{#if $config?.features.enable_ldap && $config?.features.enable_login_form}
								<div class="mt-2">
									<button
										class="flex justify-center items-center text-xs w-full text-center underline text-gray-500 dark:text-gray-400"
										type="button"
										on:click={() => {
											if (mode === 'ldap')
												mode = ($config?.onboarding ?? false) ? 'signup' : 'signin';
											else mode = 'ldap';
										}}
									>
										<span
											>{mode === 'ldap'
												? $i18n.t('Continue with Email')
												: $i18n.t('Continue with LDAP')}</span
										>
									</button>
								</div>
							{/if}
						</div>
						{#if $config?.metadata?.login_footer}
							<div class="max-w-3xl mx-auto mt-4">
								<div class="text-[0.7rem] text-gray-500 dark:text-gray-400 marked">
									{@html DOMPurify.sanitize(marked($config?.metadata?.login_footer))}
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
