<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { onMount, getContext } from 'svelte';

	import { user, config, settings } from '$lib/stores';
	import { updateUserProfile, getSessionUser } from '$lib/apis/auths';
	// import { createAPIKey, getAPIKey } from '$lib/apis/auths';
	// import { WEBUI_BASE_URL } from '$lib/constants';

	import UpdatePassword from './Account/UpdatePassword.svelte';
	// import { getGravatarUrl } from '$lib/apis/utils';
	import { generateInitialsImage, canvasPixelTest } from '$lib/utils';
	// import { copyToClipboard } from '$lib/utils';
	// import Plus from '$lib/components/icons/Plus.svelte';
	// import Tooltip from '$lib/components/common/Tooltip.svelte';
	// import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	// import Textarea from '$lib/components/common/Textarea.svelte';
	// import User from '$lib/components/icons/User.svelte';
	import UserProfileImage from './Account/UserProfileImage.svelte';

	const i18n = getContext('i18n');

	// Convert any error value (string / Error / Pydantic detail array / object)
	// into a user-readable string so toast.error() never shows "[object Object]".
	const formatError = (err: unknown): string => {
		if (err == null) return '';
		if (typeof err === 'string') return err;
		if (Array.isArray(err)) {
			return err
				.map((item) =>
					typeof item === 'string' ? item : (item?.msg ?? JSON.stringify(item))
				)
				.join('; ');
		}
		if (typeof err === 'object') {
			const anyErr = err as any;
			return anyErr?.msg ?? anyErr?.message ?? anyErr?.detail ?? JSON.stringify(err);
		}
		return String(err);
	};

	export let saveHandler: Function;
	export let saveSettings: Function;

	let loaded = false;

	let profileImageUrl = '';
	let name = '';
	// let bio = '';

	// let _gender = '';
	// let gender = '';
	// let dateOfBirth = '';

	// let webhookUrl = '';
	// let showAPIKeys = false;

	// let JWTTokenCopied = false;

	// let APIKey = '';
	// let APIKeyCopied = false;
	// let profileImageInputElement: HTMLInputElement;

	const submitHandler = async () => {
		if (name !== $user?.name) {
			if (profileImageUrl === generateInitialsImage($user?.name) || profileImageUrl === '') {
				profileImageUrl = generateInitialsImage(name);
			}
		}

		// if (webhookUrl !== $settings?.notifications?.webhook_url) {
		// 	saveSettings({
		// 		notifications: {
		// 			...$settings.notifications,
		// 			webhook_url: webhookUrl
		// 		}
		// 	});
		// }

		const updatedUser = await updateUserProfile(localStorage.token, {
			name: name,
			profile_image_url: profileImageUrl
			// bio: bio ? bio : null,
			// gender: gender ? gender : null,
			// date_of_birth: dateOfBirth ? dateOfBirth : null
		}).catch((error) => {
			toast.error(formatError(error));
		});

		if (updatedUser) {
			const sessionUser = await getSessionUser(localStorage.token).catch((error) => {
				toast.error(formatError(error));
				return null;
			});

			await user.set(sessionUser);
			return true;
		}
		return false;
	};

	// const createAPIKeyHandler = async () => {
	// 	APIKey = await createAPIKey(localStorage.token);
	// 	if (APIKey) {
	// 		toast.success($i18n.t('API Key created.'));
	// 	} else {
	// 		toast.error($i18n.t('Failed to create API Key.'));
	// 	}
	// };

	onMount(async () => {
		const user = await getSessionUser(localStorage.token).catch((error) => {
			toast.error(formatError(error));
			return null;
		});

		if (user) {
			name = user?.name ?? '';
			profileImageUrl = user?.profile_image_url ?? '';
			// bio = user?.bio ?? '';

			// _gender = user?.gender ?? '';
			// gender = _gender;

			// dateOfBirth = user?.date_of_birth ?? '';
		}

		// webhookUrl = $settings?.notifications?.webhook_url ?? '';

		// // Only fetch API key if the feature is enabled and user has permission
		// if (
		// 	user &&
		// 	($config?.features?.enable_api_keys ?? true) &&
		// 	(user?.role === 'admin' || (user?.permissions?.features?.api_keys ?? false))
		// ) {
		// 	APIKey = await getAPIKey(localStorage.token).catch((error) => {
		// 		console.log(error);
		// 		return '';
		// 	});
		// }

		loaded = true;
	});
</script>

<div id="tab-account" class="flex flex-col h-full justify-between text-sm">
	<div class="space-y-5">
		<div class="flex items-start gap-5">
			<UserProfileImage bind:profileImageUrl user={$user} />

			<div class="flex-1 space-y-3">
				<div class="flex flex-col w-full">
					<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Email')}</label>
					<div class="px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40">
						<input
							class="w-full text-sm text-gray-400 dark:text-gray-500 bg-transparent outline-hidden cursor-not-allowed"
							type="email"
							value={$user?.email ?? ''}
							aria-label={$i18n.t('Email')}
							disabled
						/>
					</div>
				</div>

				<div class="flex flex-col w-full">
					<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Name')}</label>
					<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
						<input
							class="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden"
							type="text"
							bind:value={name}
							aria-label={$i18n.t('Name')}
							required
							placeholder={$i18n.t('Enter your name')}
						/>
					</div>
				</div>
			</div>
		</div>

		{#if $config?.features.enable_login_form}
			<div class="border-t border-gray-100 dark:border-gray-800 pt-5">
				<UpdatePassword />
			</div>
		{/if}
	</div>

	<div class="flex justify-end pt-5 mt-4 border-t border-gray-100 dark:border-gray-800">
		<button
			class="px-4 py-1.5 text-sm font-medium bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 transition-all rounded-lg shadow-sm"
			on:click={async () => {
				const res = await submitHandler();
				if (res) {
					saveHandler();
				}
			}}
		>
			{$i18n.t('Save')}
		</button>
	</div>
</div>
