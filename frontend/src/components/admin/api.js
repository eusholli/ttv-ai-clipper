export const fetchJobs = async (getToken) => {
  try {
    const token = await getToken();
    const response = await fetch('/api/admin/jobs', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    if (!response.ok) throw new Error('Failed to fetch jobs');
    return await response.json();
  } catch (err) {
    console.error('Error fetching jobs:', err);
    throw new Error('Failed to fetch jobs');
  }
};

export const fetchJobDetails = async (jobId, getToken) => {
  try {
    const token = await getToken();
    const response = await fetch(`/api/admin/jobs/${jobId}/details`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    if (!response.ok) throw new Error('Failed to fetch job details');
    return await response.json();
  } catch (err) {
    console.error('Error fetching job details:', err);
    throw new Error('Failed to fetch job details');
  }
};

export const fetchJobLog = async (jobId, getToken) => {
  try {
    const token = await getToken();
    const response = await fetch(`/api/admin/jobs/${jobId}/log`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    if (!response.ok) throw new Error('Failed to fetch job log');
    return await response.json();
  } catch (err) {
    console.error('Error fetching job log:', err);
    throw new Error('Failed to fetch job log');
  }
};

export const createJob = async (urls, email, getToken, autoApprove = false) => {
  try {
    const token = await getToken();
    const response = await fetch('/api/admin/jobs', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ urls, user_email: email, auto_approve: autoApprove })
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || 'Failed to create job');
    }

    return await response.json();
  } catch (err) {
    console.error('Error creating job:', err);
    throw err;
  }
};

export const updateContent = async (jobId, content, getToken) => {
  try {
    const token = await getToken();
    // Ensure content follows the new Transcript model structure
    const transcriptData = {
      metadata: content.metadata,
      raw_transcript: content.raw_transcript,
      transcript: content.transcript
    };

    const response = await fetch(`/api/admin/jobs/${jobId}/content`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ transcript: transcriptData })
    });

    if (!response.ok) throw new Error('Failed to update content');
    const data = await response.json();
    return {
      status: data.status,
      parsing_status: data.parsing_status
    };
  } catch (err) {
    console.error('Error updating content:', err);
    throw err;
  }
};

export const deleteArchive = async (getToken) => {
  try {
    const token = await getToken();
    const response = await fetch('/api/admin/jobs/archive', {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) throw new Error('Failed to delete archive');
    return await response.json();
  } catch (err) {
    console.error('Error deleting archive:', err);
    throw err;
  }
};

export const validateContent = async (jobId, content, getToken) => {
  try {
    const token = await getToken();
    // Ensure content follows the new Transcript model structure
    const transcriptData = {
      metadata: content.metadata,
      raw_transcript: content.raw_transcript,
      transcript: content.transcript
    };

    const response = await fetch(`/api/admin/jobs/${jobId}/validate`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ transcript: transcriptData })
    });

    if (!response.ok) throw new Error('Failed to validate content');
    return await response.json();
  } catch (err) {
    console.error('Error validating content:', err);
    throw err;
  }
};

export const processTranscript = async (jobId, getToken) => {
  try {
    const token = await getToken();
    const response = await fetch(`/api/admin/jobs/${jobId}/process-transcript`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) throw new Error('Failed to process transcript');
    return await response.json();
  } catch (err) {
    console.error('Error processing transcript:', err);
    throw err;
  }
};

export const deleteContent = async (jobId, getToken) => {
  try {
    const token = await getToken();
    const response = await fetch(`/api/admin/jobs/${jobId}/content`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) throw new Error('Failed to delete content');
    return await response.json();
  } catch (err) {
    console.error('Error deleting content:', err);
    throw err;
  }
};
