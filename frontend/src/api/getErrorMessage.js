// The Flask backend returns errors as { "error": "..." }.
// This pulls that message out, with sensible fallbacks for network failures.
export function getErrorMessage(err) {
  if (err.response && err.response.data && err.response.data.error) {
    return err.response.data.error;
  }
  if (err.request) {
    return "Could not reach the server. Is the backend running?";
  }
  return "Something went wrong. Please try again.";
}
